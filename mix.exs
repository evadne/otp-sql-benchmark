defmodule BeamSqlBench.MixProject do
  use Mix.Project

  def project do
    [
      app: :beam_sql_bench,
      version: "0.1.0",
      elixir: "~> 1.19",
      deps: [
        {:sql, "== 0.5.0"},
        {:postgrex, "== 0.22.4"},
        {:ecto_sql, "== 3.14.0"},
        {:epgsql, "== 4.8.0"},
        {:jason, "~> 1.4"}
      ]
    ]
  end

  def application, do: [extra_applications: [:logger]]
end
