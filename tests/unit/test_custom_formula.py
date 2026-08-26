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


def test_custom_formula_supports_dynamic_ref_periods() -> None:
    parsed = parse_formula("W1:C=HHV(C,3); W2:=BARSLAST(W1); LEVEL:REF(C,W2);")
    result = evaluate_custom_formula(parsed, bars())

    assert "custom.w1" in {signal.id for signal in parsed.signals}
    assert result.last_indicator_values["LEVEL"] == 80.0


def test_custom_formula_has_warmup_and_safe_zero_division() -> None:
    parsed = parse_formula("N:=5; ZERO:C/(C-C)+REF(C,N);")
    result = evaluate_custom_formula(parsed, bars(3))

    assert result.sufficient_data is False
    assert result.last_signal_state["custom.zero"] is False
    assert not np.isinf(result.values["ZERO"]).any()


def test_the_three_supplied_formula_shapes_are_parseable() -> None:
    indicator_one = """
    VAR1:=REF((LOW+OPEN+CLOSE+HIGH)/4,1);
    VAR2:=SMA(ABS(LOW-VAR1),13,1)/SMA(MAX(LOW-VAR1,0),10,1);
    VAR3:=EMA(VAR2,10); VAR4:=LLV(LOW,33);
    VAR5:=EMA(IF(LOW<=VAR4,VAR3,0),3);
    主力进场:IF(VAR5>REF(VAR5,1),VAR5,0);
    """
    indicator_two = """
    短线成本:=EMA(CLOSE,17); A:=(3*C+L+O+H)/6;
    X:=(20*A+19*REF(A,1)+18*REF(A,2)+17*REF(A,3)+16*REF(A,4)+15*REF(A,5)+14*REF(A,6)+13*REF(A,7)+12*REF(A,8)+11*REF(A,9)+10*REF(A,10)+9*REF(A,11)+8*REF(A,12)+7*REF(A,13)+6*REF(A,14)+5*REF(A,15)+4*REF(A,16)+3*REF(A,17)+2*REF(A,18)+REF(A,20))/210;
    中线成本:=EMA(X,13); VAR1:=1; VAR2:=LLV(LOW,10); VAR3:=HHV(HIGH,25); N1:=5; N4:=34;
    CQ:=100*(C-LLV(L,N4))/(HHV(C,N4)-LLV(L,N4));
    W1:=C=HHV(C,20); W2:=BARSLAST(W1); W3:=IF(W2>0,REF(C,W2),REF(C,W2)); W4:=CROSS(C,REF(W3,1));
    中期:=CQ;
    持股:=3*SMA((CLOSE-LLV(LOW,27))/(HHV(HIGH,27)-LLV(LOW,27))*100,5,1)
    -2*SMA(SMA((CLOSE-LLV(LOW,27))/(HHV(HIGH,27)-LLV(LOW,27))*100,5,1),3,1);
    """
    indicator_three = """
    N:=5;
    VAR1:4*SMA((CLOSE-LLV(LOW,N))/(HHV(HIGH,N)-LLV(LOW,N))*100,5,1)
    -3*SMA(SMA((CLOSE-LLV(LOW,N))/(HHV(HIGH,N)-LLV(LOW,N))*100,5,1),3.2,1);
    VAR2:8; 准备拉升:IF(CROSS(VAR1,VAR2),80,0); 压住庄家:IF(VAR1<=8,25,0);
    VARO5:=LLV(LOW,27); VARO6:=HHV(HIGH,34);
    VARO7:=EMA((CLOSE-VARO5)/(VARO6-VARO5)*4,4)*25;
    建仓区:IF(VARO7<10,80,100);
    """

    for source in (indicator_one, indicator_two, indicator_three):
        parsed = parse_formula(source)
        result = evaluate_custom_formula(parsed, bars())
        assert result.data_length == 80
        assert result.values


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
