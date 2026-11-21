#!/usr/bin/env python3
"""check_prices: .agents/ai-usage/model-pricing.yaml is complete and valid.

Every model has all five token-class rates as positive numbers; each provider block has an
https source_url and a verified_on date that is not in the future. A block older than
stale_after_days prints a warning and never blocks.
"""
from __future__ import annotations

import sys

try:
    from helpers.ai_usage_footer import PRICING_FILE, check_prices, load_pricing
    from helpers.govlib import report
except ModuleNotFoundError:
    from ai_usage_footer import PRICING_FILE, check_prices, load_pricing  # type: ignore
    from govlib import report  # type: ignore

NAME = "check_prices"


def main() -> int:
    errors, warnings = check_prices(load_pricing(PRICING_FILE))
    return report(NAME, errors, warnings)


if __name__ == "__main__":
    sys.exit(main())
