defmodule BeamSqlBench.WindowsTest do
  use ExUnit.Case, async: true

  test "an operation spanning every deadline is counted once, in its start window" do
    start = System.monotonic_time(:nanosecond)
    interval = 20_000_000

    op = fn ->
      Process.sleep(80)
      :ok
    end

    {count, finished, windows} =
      BeamSqlBench.timed_windows(op, start, start + 3 * interval, interval)

    assert count == 1
    assert Enum.map(windows, & &1.count) == [1, 0, 0]
    assert finished - start >= 80_000_000
    assert Enum.sum(Enum.map(windows, & &1.count)) == count
  end

  test "disabled windows preserve the original count and elapsed time" do
    start = System.monotonic_time(:nanosecond)

    op = fn ->
      Process.sleep(30)
      :ok
    end

    {count, finished, windows} = BeamSqlBench.timed_windows(op, start, start + 10_000_000, 0)
    assert count == 1
    assert windows == []
    assert finished - start >= 30_000_000
  end
end
