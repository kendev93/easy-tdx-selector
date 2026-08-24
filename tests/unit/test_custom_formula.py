from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from selector_app.formulas.custom import (
    FormulaParseError,
    evaluate_custom_formula,
    parse_formula,
)


def bars(length: int = 80) -> pd.DataFrame:
    close = np.arange(1.0, length + 1)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=length, freq="D"),
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(length, 100_000.0),
            "amount": close * 100_000.0,
        }
    )


def test_parser_extracts_explicit_parameters_and_named_outputs() -> None:
    parsed = parse_formula("N:=3; A:=EMA(C,N); BREAKOUT:CROSS(C,REF(A,1)),COLORRED;")

    assert [(parameter.name, parameter.default) for parameter in parsed.parameters] == [("N", 3.0)]
    assert [signal.id for signal in parsed.signals] == ["custom.breakout"]
    assert parsed.signals[0].display_name == "BREAKOUT"


def test_parameter_override_changes_formula_result_without_future_data() -> None:
    parsed = parse_formula("N:=2; LEVEL:REF(C,N);")
    original = evaluate_custom_formula(parsed, bars(), {"N": 2})
    overridden = evaluate_custom_formula(parsed, bars(), {"N": 5})

    assert original.sufficient_data is True
    assert original.last_indicator_values["LEVEL"] == 78.0
    assert overridden.last_indicator_values["LEVEL"] == 75.0
    assert (
        np.allclose(original.values["LEVEL"][:-1], overridden.values["LEVEL"][:-1], equal_nan=True)
        is False
    )


def test_formula_outputs_are_selectable_boolean_signals() -> None:
    parsed = parse_formula("N:=2; BREAKOUT:CROSS(C,REF(C,N));")
    result = evaluate_custom_formula(parsed, bars())

    assert result.signals["custom.breakout"].any()
    assert result.signals["custom.breakout"].dtype == bool


def test_custom_formula_has_warmup_and_safe_zero_division() -> None:
    parsed = parse_formula("N:=5; ZERO:C/(C-C)+REF(C,N);")
    result = evaluate_custom_formula(parsed, bars(3))

    assert result.sufficient_data is False
    assert result.last_signal_state["custom.zero"] is False
    assert not np.isinf(result.values["ZERO"]).any()


@pytest.mark.parametrize(
    "formula",
    [
        "X:__import__('os').system('touch /tmp/pwned');",
        "X:(lambda: 1)();",
        "X:open('secret.txt');",
        "X:[1, 2, 3];",
    ],
)
def test_unsafe_expression_is_rejected_without_execution(formula: str) -> None:
    with pytest.raises(FormulaParseError):
        parse_formula(formula)


def test_formula_size_and_statement_limits_are_enforced() -> None:
    with pytest.raises(FormulaParseError, match="长度"):
        parse_formula("X:1;" + " " * 20_001)
    with pytest.raises(FormulaParseError, match="语句"):
        parse_formula(";".join(f"X{i}:1" for i in range(101)))
