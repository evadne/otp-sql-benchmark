defmodule BeamSqlBench.SQLClient do
  # Equivalent sigil configuration without `use SQL`'s compile-time database
  # connection/schema discovery. The actual pool starts before measurement.
  import SQL
  @sql_pool :default
  @sql_config %{
    case: :lower,
    columns: [],
    adapter: SQL.Adapters.Postgres,
    validate: fn _, _ -> true end
  }

  def empty do
    SQL.transaction do
      :ok
    end
  end

  # The unmodified library does not acknowledge COMMIT to the caller. A query on
  # the caller's cached connection fences preceding messages once per phase.
  def fence do
    [[1]] = Enum.to_list(~SQL"SELECT 1")
    :ok
  end
end
