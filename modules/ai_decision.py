import requests
import json
import logging
from typing import Dict, List, Optional
import re

logger = logging.getLogger(__name__)

class OllamaAIDecider:
    def __init__(self, config: dict):
        self.config = config
        self.base_url = config['ollama']['base_url']
        self.model = config['ollama']['model']
        self.timeout = config['ollama']['timeout_seconds']
        self.enabled = config['ollama']['enabled']

    def is_available(self) -> bool:
        """Check if Ollama server is available."""
        if not self.enabled:
            logger.info("Ollama disabled in config")
            return False

        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama not available: {str(e)}")
            return False

    def build_prompt(self, candidates: List[Dict], portfolio_state: Dict) -> str:
        """Build a concise prompt for AI review."""
        prompt = f"""You are a risk-controlled trading decision maker. Review these {len(candidates)} trade candidates and decide which to execute.

PORTFOLIO STATE:
- Cash: ${portfolio_state['cash']:.2f}
- Open positions: {portfolio_state['open_positions']}
- Max allowed: {portfolio_state['max_positions']}
- Account equity: ${portfolio_state['equity']:.2f}

TRADE CANDIDATES (scored 0-100):
"""
        for i, signal in enumerate(candidates, 1):
            prompt += f"""
{i}. {signal['symbol']} (score={signal['score']})
   Trend: {signal['trend_state']}, RSI: {signal['rsi']}, Momentum: {signal['momentum_percent']:.1f}%,
   Volume: {signal['volume_ratio']:.1f}x, Volatility: {signal['atr_percent']:.1f}%,
   Relative strength: {signal['relative_strength_percent']:.1f}%
   Notes: {signal['notes']}
"""

        prompt += f"""
RULES:
1. Only approve signals with score >= {self.config['signals']['min_score_for_ai']}
2. Do NOT trade if cash < ${self.config['trading']['position_size_min_percent'] * portfolio_state['equity'] / 100:.2f}
3. Max {self.config['trading']['max_open_positions']} open positions total
4. Position size: 5-10% of account (${{size_min}}-${{size_max}})
5. Every trade MUST have stop loss and take profit
6. If uncertain, respond "HOLD" - capital preservation is priority

RESPOND WITH ONLY VALID JSON (no other text):
[{{"symbol": "SYM", "action": "BUY"|"SKIP", "confidence": 0-100, "position_size_percent": 5-10, "stop_loss_percent": 3, "take_profit_percent": 6, "reasoning": "brief reason"}}]
"""
        return prompt

    def get_ai_decisions(self, candidates: List[Dict], portfolio_state: Dict) -> Optional[List[Dict]]:
        """Get AI decisions for trade candidates."""
        if not self.is_available():
            if self.config['ollama']['fallback_on_error']:
                logger.info("Ollama unavailable, falling back to rules")
                return self._fallback_decisions(candidates)
            return None

        try:
            prompt = self.build_prompt(candidates, portfolio_state)

            response = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout
            )

            if response.status_code != 200:
                logger.error(f"Ollama error: {response.status_code}")
                return self._fallback_decisions(candidates) if self.config['ollama']['fallback_on_error'] else None

            data = response.json()
            response_text = data.get('response', '').strip()

            # Extract JSON from response
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if not json_match:
                logger.warning("No valid JSON in AI response")
                return self._fallback_decisions(candidates) if self.config['ollama']['fallback_on_error'] else None

            decisions = json.loads(json_match.group())
            logger.info(f"AI made {len(decisions)} decisions")
            return self._validate_decisions(decisions)

        except Exception as e:
            logger.error(f"AI decision failed: {str(e)}")
            return self._fallback_decisions(candidates) if self.config['ollama']['fallback_on_error'] else None

    def _validate_decisions(self, decisions: List[Dict]) -> List[Dict]:
        """Validate AI output format."""
        validated = []
        for d in decisions:
            if not isinstance(d, dict):
                continue

            valid = {
                'symbol': d.get('symbol', '').upper(),
                'action': d.get('action', 'SKIP').upper(),
                'confidence': min(100, max(0, d.get('confidence', 50))),
                'position_size_percent': min(
                    self.config['trading']['position_size_max_percent'],
                    max(self.config['trading']['position_size_min_percent'], d.get('position_size_percent', 5))
                ),
                'stop_loss_percent': max(0.5, d.get('stop_loss_percent', 3)),
                'take_profit_percent': max(1, d.get('take_profit_percent', 6)),
                'reasoning': str(d.get('reasoning', ''))[:100]
            }

            if valid['action'] in ['BUY', 'SKIP']:
                validated.append(valid)

        return validated

    def _fallback_decisions(self, candidates: List[Dict]) -> List[Dict]:
        """Fallback to rule-based decisions when AI fails."""
        logger.info("Using fallback rule-based decisions")
        decisions = []

        for signal in candidates:
            decision = {
                'symbol': signal['symbol'],
                'action': 'BUY' if signal['score'] >= self.config['signals']['auto_approve_score'] else 'SKIP',
                'confidence': min(100, signal['score']),
                'position_size_percent': self.config['trading']['position_size_min_percent'] + (signal['score'] - 50) * 0.1,
                'stop_loss_percent': self.config['trading']['stop_loss_percent'],
                'take_profit_percent': self.config['trading']['take_profit_percent'],
                'reasoning': f"fallback: score {signal['score']}"
            }
            decision['position_size_percent'] = min(
                self.config['trading']['position_size_max_percent'],
                max(self.config['trading']['position_size_min_percent'], decision['position_size_percent'])
            )
            decisions.append(decision)

        return decisions
