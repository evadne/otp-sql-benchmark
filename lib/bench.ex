defmodule BeamSqlBench.Repo do
  use Ecto.Repo, otp_app: :beam_sql_bench, adapter: Ecto.Adapters.Postgres
end

defmodule BeamSqlBench.NoIO do
  use DBConnection
  def connect(_), do: {:ok, :idle}
  def disconnect(_, _), do: :ok
  def checkout(state), do: {:ok, state}
  def ping(state), do: {:ok, state}
  def handle_begin(_, :idle), do: {:ok, :begun, :transaction}
  def handle_commit(_, :transaction), do: {:ok, :committed, :idle}
  def handle_rollback(_, :transaction), do: {:ok, :rolled_back, :idle}
  def handle_status(_, state), do: {state, state}
  def handle_prepare(_, _, _), do: raise("no SQL in the no-I/O control")
  def handle_execute(_, _, _, _), do: raise("no SQL in the no-I/O control")
  def handle_close(_, _, _), do: raise("no SQL in the no-I/O control")
  def handle_declare(_, _, _, _), do: raise("no SQL in the no-I/O control")
  def handle_fetch(_, _, _, _), do: raise("no SQL in the no-I/O control")
  def handle_deallocate(_, _, _, _), do: raise("no SQL in the no-I/O control")
end

defmodule BeamSqlBench do
  @moduledoc "Closed-loop empty transaction benchmark; API completions and final drain times are recorded separately."
  alias BeamSqlBench.Repo

  def options do
    [
      hostname: System.get_env("PGHOST", "127.0.0.1"),
      port: int("PGPORT", 55432),
      username: "postgres",
      database: "beam_bench",
      ssl: false,
      timeout: 30_000,
      queue_target: 10_000,
      queue_interval: 10_000,
      show_sensitive_data_on_connection_error: false,
      parameters: [application_name: "beam_sql_bench"]
    ]
  end

  def run do
    mode = System.fetch_env!("BENCH_MODE")
    workers = int("WORKERS", 10)
    seconds = int("SECONDS_PER_RUN", 60)
    warmup = int("WARMUP_SECONDS", 10)
    window = int("WINDOW_SECONDS", 0)
    repeats = int("REPEATS", 3)
    pool_size = int("POOL_SIZE", :erlang.system_info(:schedulers_online))
    true = seconds > 0 and warmup >= 0 and window >= 0
    true = window == 0 or rem(seconds, window) == 0
    {shared, stop} = setup(mode, pool_size)

    metadata = %{
      mode: mode,
      workers: workers,
      pool_size: if(mode in ["epgsql", "epgsql_batch"], do: workers, else: pool_size),
      seconds: seconds,
      warmup_seconds: warmup,
      window_seconds: window,
      schedulers: :erlang.system_info(:schedulers),
      schedulers_online: :erlang.system_info(:schedulers_online),
      dirty_cpu_schedulers: :erlang.system_info(:dirty_cpu_schedulers_online),
      otp: to_string(:erlang.system_info(:otp_release)),
      elixir: System.version(),
      erts: to_string(:erlang.system_info(:version)),
      cpu_affinity: affinity(),
      pg_host: System.get_env("PGHOST", "127.0.0.1"),
      timestamp: DateTime.utc_now() |> DateTime.to_iso8601(),
      deps:
        Map.new(
          [:sql, :postgrex, :ecto_sql, :ecto, :epgsql, :db_connection],
          &{&1, to_string(Application.spec(&1, :vsn))}
        )
    }

    try do
      for repeat <- 1..repeats do
        result = measure(mode, shared, workers, warmup, seconds, window)
        IO.puts(Jason.encode!(Map.merge(metadata, Map.put(result, :repeat, repeat))))
      end
    after
      stop.()
    end
  end

  defp setup("sql", size) do
    ^size = :erlang.system_info(:schedulers_online)

    opts = [
      username: "postgres",
      password: "",
      database: "beam_bench",
      hostname: System.get_env("PGHOST", "127.0.0.1"),
      addr:
        System.get_env("PGHOST", "127.0.0.1")
        |> String.to_charlist()
        |> :inet.parse_address()
        |> elem(1),
      port: int("PGPORT", 55432),
      adapter: SQL.Adapters.Postgres,
      ssl: false
    ]

    Application.stop(:sql)
    Application.put_env(:sql, :pools, default: opts)
    {:ok, _} = Application.ensure_all_started(:sql)
    {nil, fn -> Application.stop(:sql) end}
  end

  defp setup("no_io", size) do
    {:ok, pid} = DBConnection.start_link(BeamSqlBench.NoIO, pool_size: size)
    {pid, fn -> Supervisor.stop(pid) end}
  end

  defp setup("ecto", size) do
    {:ok, pid} = Repo.start_link(options() ++ [pool_size: size, log: false])
    Repo.query!("SELECT 1")
    {pid, fn -> Supervisor.stop(pid) end}
  end

  defp setup(mode, size) when mode in ["postgrex", "postgrex_held"] do
    {:ok, pid} = Postgrex.start_link(options() ++ [pool_size: size])
    Postgrex.query!(pid, "SELECT 1", [])
    {pid, fn -> Supervisor.stop(pid) end}
  end

  defp setup(mode, _) when mode in ["epgsql", "epgsql_batch"], do: {nil, fn -> :ok end}

  defp measure(mode, shared, workers, warmup, seconds, window) do
    parent = self()

    tasks =
      for _ <- 1..workers do
        Task.async(fn ->
          with_operation(mode, shared, fn op, drain ->
            loop(op, now() + warmup * 1_000_000_000, 0)
            :ok = drain.()
            send(parent, {:ready, self()})

            receive do
              {:go, start, deadline} ->
                wait_until(start)

                {count, finished, windows} =
                  timed_windows(op, start, deadline, window * 1_000_000_000)

                :ok = drain.()
                %{count: count, api_finished: finished, finished: now(), windows: windows}
            after
              60_000 -> raise "start barrier timed out"
            end
          end)
        end)
      end

    for _ <- 1..workers do
      receive do
        {:ready, _} -> :ok
      after
        60_000 -> raise "worker warmup timed out"
      end
    end

    {reductions_before, _} = :erlang.statistics(:reductions)
    {runtime_before, _} = :erlang.statistics(:runtime)
    start = now() + 100_000_000
    deadline = start + seconds * 1_000_000_000
    Enum.each(tasks, &send(&1.pid, {:go, start, deadline}))
    results = Enum.map(tasks, &Task.await(&1, (seconds + 60) * 1000))
    {runtime_after, _} = :erlang.statistics(:runtime)
    {reductions_after, _} = :erlang.statistics(:reductions)
    count = Enum.sum(Enum.map(results, & &1.count))
    elapsed = (Enum.max(Enum.map(results, & &1.finished)) - start) / 1.0e9

    %{
      transactions: count,
      elapsed_seconds: elapsed,
      tps: count / elapsed,
      errors: if(mode == "sql", do: nil, else: 0),
      api_tps: count / ((Enum.max(Enum.map(results, & &1.api_finished)) - start) / 1.0e9),
      drain_seconds:
        (Enum.max(Enum.map(results, & &1.finished)) -
           Enum.max(Enum.map(results, & &1.api_finished))) / 1.0e9,
      worker_counts: Enum.map(results, & &1.count),
      windows:
        results
        |> Enum.map(& &1.windows)
        |> Enum.zip()
        |> Enum.with_index()
        |> Enum.map(fn {entries, index} ->
          entries = Tuple.to_list(entries)
          counts = Enum.map(entries, & &1.count)

          %{
            start_seconds: index * window,
            end_seconds: (index + 1) * window,
            transactions: Enum.sum(counts),
            api_started_tps: Enum.sum(counts) / window,
            worker_counts: counts,
            last_api_finished_seconds:
              (Enum.max(Enum.map(entries, & &1.finished)) - start) / 1.0e9
          }
        end),
      beam_runtime_ms: runtime_after - runtime_before,
      reductions_per_transaction: (reductions_after - reductions_before) / max(count, 1)
    }
  end

  # Keep the original per-transaction loop. Window boundaries neither reconnect
  # nor drain: an operation crossing a boundary belongs to its start window.
  # All window counts are reported only after every operation and final fence.
  @doc false
  def timed_windows(op, _start, deadline, 0) do
    {count, finished} = loop(op, deadline, 0)
    {count, finished, []}
  end

  def timed_windows(op, start, deadline, interval) when interval > 0 and deadline > start do
    true = rem(deadline - start, interval) == 0

    {windows, finished} =
      Enum.map_reduce(1..div(deadline - start, interval), start, fn index, _ ->
        {count, finished} = loop(op, start + index * interval, 0)
        {%{count: count, finished: finished}, finished}
      end)

    {Enum.sum(Enum.map(windows, & &1.count)), finished, windows}
  end

  # Check time once per transaction. Do not sample latency or touch a shared counter.
  # Count the final in-flight completion and include its time in the denominator.
  defp loop(op, deadline, count) do
    timestamp = now()

    if timestamp < deadline do
      :ok = op.()
      loop(op, deadline, count + 1)
    else
      {count, timestamp}
    end
  end

  defp with_operation("sql", _, fun) do
    fun.(&BeamSqlBench.SQLClient.empty/0, &BeamSqlBench.SQLClient.fence/0)
  end

  defp with_operation(mode, shared, fun) do
    synchronous_operation(mode, shared, fn op -> fun.(op, fn -> :ok end) end)
  end

  defp synchronous_operation("postgrex", pool, fun) do
    fun.(fn ->
      {:ok, :empty} = Postgrex.transaction(pool, fn _ -> :empty end)
      :ok
    end)
  end

  defp synchronous_operation("postgrex_held", pool, fun) do
    DBConnection.run(pool, fn conn -> synchronous_operation("postgrex", conn, fun) end,
      timeout: :infinity
    )
  end

  defp synchronous_operation("ecto", _, fun) do
    fun.(fn ->
      {:ok, :empty} = Repo.transact(fn -> {:ok, :empty} end, log: false)
      :ok
    end)
  end

  defp synchronous_operation("no_io", pool, fun) do
    fun.(fn ->
      {:ok, :empty} = DBConnection.transaction(pool, fn _ -> :empty end)
      :ok
    end)
  end

  defp synchronous_operation(mode, _, fun) when mode in ["epgsql", "epgsql_batch"] do
    {:ok, conn} =
      :epgsql.connect(%{
        host: System.get_env("PGHOST", "127.0.0.1") |> String.to_charlist(),
        port: int("PGPORT", 55432),
        username: "postgres",
        database: "beam_bench",
        timeout: 30_000,
        application_name: "beam_sql_bench"
      })

    try do
      op =
        case mode do
          "epgsql" ->
            fn ->
              :empty = :epgsql.with_transaction(conn, fn _ -> :empty end)
              :ok
            end

          "epgsql_batch" ->
            fn ->
              [{:ok, [], []}, {:ok, [], []}] = :epgsql.squery(conn, "BEGIN; COMMIT")
              :ok
            end
        end

      fun.(op)
    after
      :ok = :epgsql.close(conn)
    end
  end

  def audit do
    for mode <- ["postgrex", "postgrex_held", "ecto", "epgsql", "epgsql_batch", "no_io", "sql"] do
      {shared, stop} = setup(mode, :erlang.system_info(:schedulers_online))

      try do
        with_operation(mode, shared, fn op, drain ->
          for _ <- 1..3, do: :ok = op.()
          :ok = drain.()
        end)

        IO.puts("AUDIT_OK #{mode} 3")
      after
        stop.()
      end
    end
  end

  def completion_probe do
    mode = System.fetch_env!("BENCH_MODE")
    {shared, stop} = setup(mode, :erlang.system_info(:schedulers_online))

    try do
      with_operation(mode, shared, fn op, drain ->
        :ok = op.()
        :ok = drain.()
        IO.puts("PROBE_READY")
        "go\n" = IO.gets("")
        {microseconds, :ok} = :timer.tc(op)
        IO.puts("PROBE_RETURNED #{microseconds}")
        :ok = drain.()
        IO.puts("PROBE_DRAINED")
      end)
    after
      stop.()
    end
  end

  def count_audit do
    mode = System.fetch_env!("BENCH_MODE")
    count = int("AUDIT_COUNT", 10_000)
    workers = int("WORKERS", 10)
    {shared, stop} = setup(mode, :erlang.system_info(:schedulers_online))

    try do
      1..workers
      |> Enum.map(fn _ ->
        Task.async(fn ->
          with_operation(mode, shared, fn op, drain ->
            if count > 0 do
              for _ <- 1..count, do: :ok = op.()
            end

            :ok = drain.()
          end)
        end)
      end)
      |> Enum.each(&Task.await(&1, 60_000))

      IO.puts("COUNT_AUDIT #{mode} #{workers * count}")
    after
      stop.()
    end
  end

  defp wait_until(start) do
    remaining = start - now()

    if remaining > 0 do
      Process.sleep(max(div(remaining, 1_000_000), 1))
      wait_until(start)
    end
  end

  defp affinity do
    File.read!("/proc/self/status")
    |> String.split("\n")
    |> Enum.find(&String.starts_with?(&1, "Cpus_allowed_list:"))
  end

  defp now, do: System.monotonic_time(:nanosecond)
  defp int(name, default), do: System.get_env(name, to_string(default)) |> String.to_integer()
end
