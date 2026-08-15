from eval_harness.metrics import prf


def test_perfect_retrieval_scores_one():
    assert prf(predicted={"a.py", "b.py"}, truth={"a.py", "b.py"}) == (1.0, 1.0, 1.0)


def test_half_the_truth_found_and_nothing_spurious():
    # blindfold: math — 2 of 2 predicted are right (P=1.0), 2 of 4 truths found (R=0.5),
    # F1 = 2PR/(P+R) = 2(1.0)(0.5)/1.5 = 0.667.
    precision, recall, f1 = prf({"a.py", "b.py"}, {"a.py", "b.py", "c.py", "d.py"})
    assert (precision, recall, round(f1, 3)) == (1.0, 0.5, 0.667)


def test_over_prediction_is_punished_in_precision_not_recall():
    # blindfold: math — 2 of 4 predicted are right (P=0.5), both truths found (R=1.0).
    precision, recall, _ = prf({"a.py", "b.py", "x.py", "y.py"}, {"a.py", "b.py"})
    assert (precision, recall) == (0.5, 1.0)


def test_predicting_nothing_scores_zero_rather_than_dividing_by_zero():
    assert prf(set(), {"a.py"}) == (0.0, 0.0, 0.0)


def test_an_empty_truth_set_scores_zero_because_the_question_was_unanswerable():
    """A symbol nothing references is not a win for either method — it is excluded
    from the sample, and scoring it zero makes that visible instead of silent."""
    assert prf({"a.py"}, set()) == (0.0, 0.0, 0.0)
