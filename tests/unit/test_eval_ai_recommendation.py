import pytest

from scripts.eval_ai_recommendation import (
    EvalOutcome,
    LabelParseError,
    LabelRow,
    compute_metrics,
    load_labels,
    parse_bool_label,
)


# -- parse_bool_label --


@pytest.mark.parametrize("raw", ["true", "True", "1", "yes", "Y", "是", "推荐"])
def test_parse_bool_label_accepts_true_spellings(raw):
    assert parse_bool_label(raw, row_num=2, column="expected_recommend") is True


@pytest.mark.parametrize("raw", ["false", "False", "0", "no", "N", "否", "不推荐"])
def test_parse_bool_label_accepts_false_spellings(raw):
    assert parse_bool_label(raw, row_num=2, column="expected_recommend") is False


def test_parse_bool_label_rejects_unrecognized_value():
    with pytest.raises(LabelParseError, match="第 5 行"):
        parse_bool_label("maybe", row_num=5, column="expected_recommend")


# -- load_labels --


def _write_csv(tmp_path, content: str):
    path = tmp_path / "labels.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_labels_parses_valid_rows(tmp_path):
    path = _write_csv(
        tmp_path,
        "item_id,task_name,expected_recommend,note\n"
        "111,MacBook,true,靠谱个人卖家\n"
        "222,MacBook,false,疑似职业商家\n",
    )

    rows = load_labels(path)

    assert rows == [
        LabelRow(item_id="111", task_name="MacBook", expected_recommend=True, note="靠谱个人卖家"),
        LabelRow(item_id="222", task_name="MacBook", expected_recommend=False, note="疑似职业商家"),
    ]


def test_load_labels_strips_leading_quote_from_item_id(tmp_path):
    # list_eval_candidates.py 给长数字 item_id 加了个前导单引号防止 Excel 转科学计数法，
    # 这里要能正确还原成原始 ID，否则会拿着一个带引号的假 ID 去数据库查，永远查不到。
    path = _write_csv(
        tmp_path,
        "item_id,task_name,expected_recommend,note\n"
        "'1234567890123,MacBook,true,\n",
    )

    rows = load_labels(path)

    assert rows == [LabelRow(item_id="1234567890123", task_name="MacBook", expected_recommend=True, note="")]


def test_load_labels_skips_rows_with_blank_item_id_or_unlabeled_expected(tmp_path, capsys):
    path = _write_csv(
        tmp_path,
        "item_id,task_name,expected_recommend,note\n"
        ",MacBook,true,空 item_id 应跳过\n"
        "333,MacBook,,还没标注应跳过\n"
        "444,MacBook,true,应保留\n",
    )

    rows = load_labels(path)

    assert [r.item_id for r in rows] == ["444"]
    assert "333" in capsys.readouterr().out


def test_load_labels_raises_with_row_number_on_bad_value(tmp_path):
    path = _write_csv(
        tmp_path,
        "item_id,task_name,expected_recommend,note\n"
        "555,MacBook,maybe,坏数据\n",
    )

    with pytest.raises(LabelParseError, match="第 2 行"):
        load_labels(path)


def test_load_labels_defaults_task_name_to_empty_when_missing_column(tmp_path):
    path = _write_csv(tmp_path, "item_id,expected_recommend\n666,true\n")

    rows = load_labels(path)

    assert rows == [LabelRow(item_id="666", task_name="", expected_recommend=True, note="")]


# -- compute_metrics --


def _outcome(item_id, expected, predicted, **kwargs):
    return EvalOutcome(
        item_id=item_id, task_name="t", title="", expected=expected, predicted=predicted, **kwargs
    )


def test_compute_metrics_confusion_matrix_and_scores():
    outcomes = [
        _outcome("1", expected=True, predicted=True),  # TP
        _outcome("2", expected=True, predicted=True),  # TP
        _outcome("3", expected=False, predicted=False),  # TN
        _outcome("4", expected=False, predicted=True),  # FP
        _outcome("5", expected=True, predicted=False),  # FN
    ]

    metrics = compute_metrics(outcomes)

    assert metrics["tp"] == 2
    assert metrics["tn"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["scored"] == 5
    assert metrics["skipped_ai_failed"] == 0
    assert metrics["accuracy"] == pytest.approx(3 / 5)
    assert metrics["precision"] == pytest.approx(2 / 3)
    assert metrics["recall"] == pytest.approx(2 / 3)
    assert metrics["f1"] == pytest.approx(2 / 3)


def test_compute_metrics_excludes_ai_failures_from_denominator():
    outcomes = [
        _outcome("1", expected=True, predicted=True, error=""),
        _outcome("2", expected=True, predicted=None, error="AI analysis returned None after retries."),
    ]

    metrics = compute_metrics(outcomes)

    assert metrics["total_labeled"] == 2
    assert metrics["scored"] == 1
    assert metrics["skipped_ai_failed"] == 1
    assert metrics["accuracy"] == 1.0


def test_compute_metrics_handles_empty_input_without_dividing_by_zero():
    metrics = compute_metrics([])

    assert metrics == {
        "total_labeled": 0,
        "scored": 0,
        "skipped_ai_failed": 0,
        "tp": 0,
        "tn": 0,
        "fp": 0,
        "fn": 0,
        "accuracy": 0.0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }
