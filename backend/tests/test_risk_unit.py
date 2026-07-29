"""Unit tests for RiskCalculator — pure math functions (no DB)."""

import pytest

from app.services.risk_calculator import (
    PIP_SIZES,
    PIP_VALUES,
    SUPPORTED_SYMBOLS,
    PositionSizeResult,
    MarginResult,
    RiskCalculationResult,
    calculate_margin,
    calculate_position_size,
    calculate_profit_targets,
    calculate_risk_metrics,
    get_all_pip_values,
    get_pip_size,
    get_pip_value,
)


# ── Pip Value Lookup ──────────────────────────────────────────────────────────

class TestPipSize:
    def test_forex_pip_size(self):
        assert get_pip_size("EURUSD") == 0.0001
        assert get_pip_size("GBPUSD") == 0.0001
        assert get_pip_size("AUDUSD") == 0.0001
        assert get_pip_size("NZDUSD") == 0.0001

    def test_usdjpy_pip_size(self):
        assert get_pip_size("USDJPY") == 0.01

    def test_usdxxx_pip_size(self):
        assert get_pip_size("USDCAD") == 0.0001
        assert get_pip_size("USDCHF") == 0.0001

    def test_xauusd_pip_size(self):
        assert get_pip_size("XAUUSD") == 0.10

    def test_crypto_pip_size(self):
        assert get_pip_size("BTCUSD") == 1.0
        assert get_pip_size("ETHUSD") == 0.10

    def test_case_insensitive(self):
        assert get_pip_size("eurusd") == 0.0001
        assert get_pip_size("BtcUsd") == 1.0

    def test_unsupported_symbol(self):
        with pytest.raises(ValueError, match="Unsupported symbol"):
            get_pip_size("ZZZ999")


class TestPipValue:
    def test_xxxusd_pairs(self):
        assert get_pip_value("EURUSD") == 10.0
        assert get_pip_value("GBPUSD") == 10.0
        assert get_pip_value("AUDUSD") == 10.0
        assert get_pip_value("NZDUSD") == 10.0

    def test_usdjpy(self):
        assert get_pip_value("USDJPY") == 9.15

    def test_usdcad(self):
        assert get_pip_value("USDCAD") == 7.50

    def test_usdchf(self):
        assert get_pip_value("USDCHF") == 11.0

    def test_xauusd(self):
        assert get_pip_value("XAUUSD") == 10.0

    def test_crypto(self):
        assert get_pip_value("BTCUSD") == 1.0
        assert get_pip_value("ETHUSD") == 0.10

    def test_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported symbol"):
            get_pip_value("ZZZZZZ")


class TestGetAllPipValues:
    def test_all_symbols_present(self):
        result = get_all_pip_values()
        assert len(result) == 10
        for sym in SUPPORTED_SYMBOLS:
            assert sym in result
            assert "pip_size" in result[sym]
            assert "pip_value_per_lot" in result[sym]


# ── Position Size Calculator ──────────────────────────────────────────────────

class TestCalculatePositionSize:
    """Verified formulas with known input/output pairs."""

    def test_eurusd_standard(self):
        """EURUSD: $10k balance, 1% risk, entry 1.0850, SL 1.0820 (30 pips)."""
        result = calculate_position_size(
            account_balance=10000.0,
            risk_percentage=1.0,
            entry_price=1.0850,
            stop_loss=1.0820,
            symbol="EURUSD",
        )
        # risk_amount = 100.00
        # stop_loss_pips = (1.0850 - 1.0820) / 0.0001 = 30.0
        # lot_count = 100 / (30.0 * 10) = 0.3333... lots
        # position_size = 0.3333 * 100000 = 33,333.33
        assert result.risk_amount == 100.0
        assert result.stop_loss_pips == 30.0
        assert result.position_size == pytest.approx(33333.33, rel=0.01)
        assert result.lot_size == pytest.approx(0.3333, rel=0.01)
        assert result.mini_lots == pytest.approx(3.33, rel=0.01)
        assert result.micro_lots == pytest.approx(33.33, rel=0.01)

    def test_eurusd_larger_account(self):
        """EURUSD: $100k balance, 2% risk, entry 1.1000, SL 1.0950 (50 pips)."""
        result = calculate_position_size(
            account_balance=100_000.0,
            risk_percentage=2.0,
            entry_price=1.1000,
            stop_loss=1.0950,
            symbol="EURUSD",
        )
        assert result.risk_amount == 2000.0
        assert result.stop_loss_pips == 50.0
        # lot_count = 2000 / (50 * 10) = 4.0 standard lots
        # position_size = 4.0 * 100000 = 400,000
        assert result.position_size == 400_000.0
        assert result.lot_size == 4.0
        assert result.mini_lots == 40.0
        assert result.micro_lots == 400.0

    def test_usdjpy(self):
        """USDJPY: entry 150.00, SL 149.50, pip_size=0.01, pip_value=9.15."""
        result = calculate_position_size(
            account_balance=5000.0,
            risk_percentage=2.0,
            entry_price=150.00,
            stop_loss=149.50,
            symbol="USDJPY",
        )
        # risk_amount = 100.0
        # sl_distance = 0.50
        # stop_loss_pips = 0.50 / 0.01 = 50.0
        # lot_count = 100 / (50 * 9.15) = 0.21858...
        # position_size = 0.21858 * 100000 = 21,858
        assert result.risk_amount == 100.0
        assert result.stop_loss_pips == 50.0
        assert result.position_size == pytest.approx(21858.0, rel=0.01)
        assert result.lot_size == pytest.approx(0.2186, rel=0.01)

    def test_xauusd(self):
        """XAUUSD (Gold): entry 1900.00, SL 1890.00, pip=0.10, value=10/lot."""
        result = calculate_position_size(
            account_balance=20000.0,
            risk_percentage=1.0,
            entry_price=1900.00,
            stop_loss=1890.00,
            symbol="XAUUSD",
        )
        # risk_amount = 200.0
        # sl_distance = 10.00
        # stop_loss_pips = 10.00 / 0.10 = 100.0
        # lot_count = 200 / (100 * 10) = 0.20
        # position_size = 0.20 * 100000 = 20,000
        assert result.risk_amount == 200.0
        assert result.stop_loss_pips == 100.0
        assert result.position_size == pytest.approx(20000.0, rel=0.01)
        assert result.lot_size == pytest.approx(0.20, rel=0.01)

    def test_btcusd(self):
        """BTCUSD: entry 50000, SL 48000, pip=1.0, value=1/lot."""
        result = calculate_position_size(
            account_balance=5000.0,
            risk_percentage=2.0,
            entry_price=50000.0,
            stop_loss=48000.0,
            symbol="BTCUSD",
        )
        # risk_amount = 100.0
        # sl_distance = 2000
        # stop_loss_pips = 2000 / 1.0 = 2000
        # lot_count = 100 / (2000 * 1) = 0.05
        # position_size = 0.05 * 100000 = 5,000
        assert result.risk_amount == 100.0
        assert result.stop_loss_pips == 2000.0
        assert result.position_size == pytest.approx(5000.0, rel=0.01)

    def test_ethusd(self):
        """ETHUSD: entry 3000, SL 2850, pip=0.10, value=0.10/lot."""
        result = calculate_position_size(
            account_balance=10000.0,
            risk_percentage=1.0,
            entry_price=3000.0,
            stop_loss=2850.0,
            symbol="ETHUSD",
        )
        # risk_amount = 100.0
        # sl_distance = 150
        # stop_loss_pips = 150 / 0.10 = 1500
        # lot_count = 100 / (1500 * 0.10) = 0.6667
        # position_size = 0.6667 * 100000 = 66,667
        assert result.risk_amount == 100.0
        assert result.stop_loss_pips == 1500.0
        assert result.position_size == pytest.approx(66666.67, rel=0.01)

    def test_sl_above_entry_short(self):
        """Short trade: entry 1.0850, SL 1.0880 — same math, |entry-sl|."""
        result = calculate_position_size(
            account_balance=10000.0,
            risk_percentage=1.0,
            entry_price=1.0850,
            stop_loss=1.0880,
            symbol="EURUSD",
        )
        assert result.risk_amount == 100.0
        assert result.stop_loss_pips == 30.0


class TestPositionSizeEdgeCases:
    def test_zero_balance(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_position_size(
                account_balance=0.0,
                risk_percentage=1.0,
                entry_price=1.0850,
                stop_loss=1.0820,
                symbol="EURUSD",
            )

    def test_negative_balance(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_position_size(
                account_balance=-1000.0,
                risk_percentage=1.0,
                entry_price=1.0850,
                stop_loss=1.0820,
                symbol="EURUSD",
            )

    def test_entry_equals_sl(self):
        with pytest.raises(ValueError, match="zero"):
            calculate_position_size(
                account_balance=10000.0,
                risk_percentage=1.0,
                entry_price=1.0850,
                stop_loss=1.0850,
                symbol="EURUSD",
            )

    def test_zero_risk(self):
        """Zero risk percentage should produce zero position size."""
        result = calculate_position_size(
            account_balance=10000.0,
            risk_percentage=0.0,
            entry_price=1.0850,
            stop_loss=1.0820,
            symbol="EURUSD",
        )
        assert result.risk_amount == 0.0
        assert result.position_size == 0.0

    def test_negative_risk(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_position_size(
                account_balance=10000.0,
                risk_percentage=-1.0,
                entry_price=1.0850,
                stop_loss=1.0820,
                symbol="EURUSD",
            )

    def test_zero_entry_price(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_position_size(
                account_balance=10000.0,
                risk_percentage=1.0,
                entry_price=0.0,
                stop_loss=1.0820,
                symbol="EURUSD",
            )

    def test_tiny_sl_distance(self):
        """Very tight SL (0.1 pip) — should still calculate correctly."""
        result = calculate_position_size(
            account_balance=10000.0,
            risk_percentage=1.0,
            entry_price=1.08500,
            stop_loss=1.08499,
            symbol="EURUSD",
        )
        # 0.00001 / 0.0001 = 0.1 pips
        assert result.stop_loss_pips == pytest.approx(0.1, rel=0.01)
        # lot_count = 100 / (0.1 * 10) = 100 lots
        # position_size = 100 * 100000 = 10,000,000
        assert result.position_size == pytest.approx(10_000_000.0, rel=0.01)


# ── Margin Calculator ─────────────────────────────────────────────────────────

class TestCalculateMargin:
    def test_standard(self):
        """$10k position, 100:1 leverage → $100 margin."""
        result = calculate_margin(
            position_size=10000.0,
            leverage=100.0,
            equity=10000.0,
        )
        assert result.required_margin == 100.0
        assert result.margin_level == 10000.0  # (10000 / 100) * 100

    def test_margin_level(self):
        """Margin level calculation."""
        result = calculate_margin(
            position_size=20000.0,
            leverage=50.0,
            equity=10000.0,
        )
        # required_margin = 20000 / 50 = 400
        # margin_level = (10000 / 400) * 100 = 2500%
        assert result.required_margin == 400.0
        assert result.margin_level == 2500.0

    def test_call_stop_levels(self):
        result = calculate_margin(position_size=5000.0, leverage=100.0)
        assert result.margin_call_level == 100.0
        assert result.stop_out_level == 50.0

    def test_no_equity_defaults_to_double(self):
        """When no equity provided, margin_level defaults to 200%."""
        result = calculate_margin(position_size=10000.0, leverage=100.0)
        # required_margin = 100, equity default = 200
        # margin_level = (200 / 100) * 100 = 200%
        assert result.margin_level == 200.0

    def test_zero_position_size(self):
        result = calculate_margin(position_size=0.0, leverage=100.0)
        assert result.required_margin == 0.0
        assert result.margin_level == float("inf")

    def test_negative_position_size(self):
        with pytest.raises(ValueError, match="non-negative"):
            calculate_margin(position_size=-1000.0, leverage=100.0)

    def test_zero_leverage(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_margin(position_size=10000.0, leverage=0.0)

    def test_negative_leverage(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_margin(position_size=10000.0, leverage=-50.0)

    def test_high_leverage(self):
        """Extreme leverage 500:1."""
        result = calculate_margin(
            position_size=100000.0,
            leverage=500.0,
            equity=5000.0,
        )
        assert result.required_margin == 200.0
        assert result.margin_level == 2500.0

    def test_tight_margin(self):
        """Near margin call scenario."""
        result = calculate_margin(
            position_size=95000.0,
            leverage=100.0,
            equity=1000.0,
        )
        # required_margin = 95000/100 = 950
        # margin_level = (1000/950) * 100 ≈ 105.26%
        assert result.required_margin == 950.0
        assert result.margin_level == pytest.approx(105.26, rel=0.01)


# ── Profit Targets ────────────────────────────────────────────────────────────

class TestCalculateProfitTargets:
    def test_long_trade(self):
        """SL below entry → long trade."""
        tp1, tp2 = calculate_profit_targets(entry_price=1.0850, stop_loss=1.0820)
        risk = 1.0850 - 1.0820  # 0.0030
        assert tp1 == pytest.approx(1.0850 + risk * 1.5, rel=1e-6)
        assert tp2 == pytest.approx(1.0850 + risk * 2.0, rel=1e-6)

    def test_short_trade(self):
        """SL above entry → short trade."""
        tp1, tp2 = calculate_profit_targets(entry_price=1.0850, stop_loss=1.0880)
        risk = 0.0030
        assert tp1 == pytest.approx(1.0850 - risk * 1.5, rel=1e-6)
        assert tp2 == pytest.approx(1.0850 - risk * 2.0, rel=1e-6)

    def test_entry_equals_sl(self):
        tp1, tp2 = calculate_profit_targets(entry_price=1.0850, stop_loss=1.0850)
        assert tp1 is None
        assert tp2 is None

    def test_large_risk_distance(self):
        tp1, tp2 = calculate_profit_targets(entry_price=100.0, stop_loss=50.0)
        assert tp1 == 100.0 + 50.0 * 1.5  # 175.0
        assert tp2 == 100.0 + 50.0 * 2.0  # 200.0


# ── Combined Risk Calculation ─────────────────────────────────────────────────

class TestCalculateRiskMetrics:
    def test_full_result_for_eurusd(self):
        result = calculate_risk_metrics(
            account_balance=10000.0,
            risk_percentage=1.0,
            entry_price=1.0850,
            stop_loss=1.0820,
            symbol="EURUSD",
            leverage=100.0,
        )
        assert isinstance(result, RiskCalculationResult)
        assert result.symbol == "EURUSD"
        assert result.risk_amount == 100.0
        assert result.stop_loss_pips == 30.0
        # lot_count = 100/(30*10) = 0.3333 lots, position_size = 33,333.33
        # required_margin = 33,333.33 / 100 = 333.33
        assert result.lot_size == pytest.approx(0.3333, rel=0.01)
        assert result.required_margin == pytest.approx(333.33, rel=0.01)
        assert result.take_profit_1 is not None
        assert result.take_profit_2 is not None
        assert result.potential_profit_tp1 is not None
        assert result.potential_profit_tp2 is not None
        # R:R should be 1.5 and 2.0
        assert result.risk_reward_ratio_tp1 == 1.5
        assert result.risk_reward_ratio_tp2 == 2.0

    def test_unsupported_symbol(self):
        with pytest.raises(ValueError, match="Unsupported symbol"):
            calculate_risk_metrics(
                account_balance=10000.0,
                risk_percentage=1.0,
                entry_price=1.0850,
                stop_loss=1.0820,
                symbol="ZZZ999",
                leverage=100.0,
            )

    def test_short_trade_metrics(self):
        """Verify short trade TPs are below entry."""
        result = calculate_risk_metrics(
            account_balance=10000.0,
            risk_percentage=1.0,
            entry_price=1.0800,
            stop_loss=1.0830,
            symbol="EURUSD",
            leverage=100.0,
        )
        assert result.take_profit_1 < result.entry_price
        assert result.take_profit_2 < result.take_profit_1


# ── Verify Constants ──────────────────────────────────────────────────────────

class TestConstants:
    def test_all_symbols_have_pip_size(self):
        for sym in SUPPORTED_SYMBOLS:
            assert sym in PIP_SIZES, f"{sym} missing pip_size"

    def test_all_symbols_have_pip_value(self):
        for sym in SUPPORTED_SYMBOLS:
            assert sym in PIP_VALUES, f"{sym} missing pip_value"

    def test_pip_values_positive(self):
        for val in PIP_VALUES.values():
            assert val > 0

    def test_pip_sizes_positive(self):
        for val in PIP_SIZES.values():
            assert val > 0
