from pacc.figures import ORDER, plot_summary


def test_plot_summary_writes_png(tmp_path):
    row = {"delta_vs_fixed": -10.0, "delta_ci95": [-15.0, -5.0], "mean": 1.0}
    summ = {"scenarios": {k: {"corridor_loss_s": row, "ev_time_s": row} for k, _ in ORDER}}
    out = tmp_path / "f.png"
    plot_summary({"700 veh/h": summ}, out)
    assert out.stat().st_size > 5000
