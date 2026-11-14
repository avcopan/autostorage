# {py:mod}`autostorage.merge`

```{py:module} autostorage.merge
```

```{autodoc2-docstring} autostorage.merge
:parser: autodoc2_docstrings_parser
:allowtitles:
```

## Module Contents

### Classes

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`MergeReport <autostorage.merge.MergeReport>`
  - ```{autodoc2-docstring} autostorage.merge.MergeReport
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### Functions

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`merge_databases <autostorage.merge.merge_databases>`
  - ```{autodoc2-docstring} autostorage.merge.merge_databases
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_is_same_database <autostorage.merge._is_same_database>`
  - ```{autodoc2-docstring} autostorage.merge._is_same_database
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_reflected_schema <autostorage.merge._reflected_schema>`
  - ```{autodoc2-docstring} autostorage.merge._reflected_schema
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_check_mergeable <autostorage.merge._check_mergeable>`
  - ```{autodoc2-docstring} autostorage.merge._check_mergeable
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_mapped_classes <autostorage.merge._mapped_classes>`
  - ```{autodoc2-docstring} autostorage.merge._mapped_classes
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_ordered_models <autostorage.merge._ordered_models>`
  - ```{autodoc2-docstring} autostorage.merge._ordered_models
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_fk_targets <autostorage.merge._fk_targets>`
  - ```{autodoc2-docstring} autostorage.merge._fk_targets
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_copy_row <autostorage.merge._copy_row>`
  - ```{autodoc2-docstring} autostorage.merge._copy_row
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_link_table_key_columns <autostorage.merge._link_table_key_columns>`
  - ```{autodoc2-docstring} autostorage.merge._link_table_key_columns
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_copy_table <autostorage.merge._copy_table>`
  - ```{autodoc2-docstring} autostorage.merge._copy_table
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_table_count <autostorage.merge._table_count>`
  - ```{autodoc2-docstring} autostorage.merge._table_count
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_copy_models <autostorage.merge._copy_models>`
  - ```{autodoc2-docstring} autostorage.merge._copy_models
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_copy_geometries <autostorage.merge._copy_geometries>`
  - ```{autodoc2-docstring} autostorage.merge._copy_geometries
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_copy_calculations <autostorage.merge._copy_calculations>`
  - ```{autodoc2-docstring} autostorage.merge._copy_calculations
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_copy_stationary_points <autostorage.merge._copy_stationary_points>`
  - ```{autodoc2-docstring} autostorage.merge._copy_stationary_points
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_copy_stages <autostorage.merge._copy_stages>`
  - ```{autodoc2-docstring} autostorage.merge._copy_stages
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_copy_identities <autostorage.merge._copy_identities>`
  - ```{autodoc2-docstring} autostorage.merge._copy_identities
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### Data

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`__all__ <autostorage.merge.__all__>`
  - ```{autodoc2-docstring} autostorage.merge.__all__
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### API

````{py:data} __all__
:canonical: autostorage.merge.__all__
:value: >
   ['MergeReport', 'merge_databases']

```{autodoc2-docstring} autostorage.merge.__all__
:parser: autodoc2_docstrings_parser
```

````

`````{py:class} MergeReport
:canonical: autostorage.merge.MergeReport

```{autodoc2-docstring} autostorage.merge.MergeReport
:parser: autodoc2_docstrings_parser
```

````{py:attribute} copied
:canonical: autostorage.merge.MergeReport.copied
:type: dict[str, int]
:value: >
   None

```{autodoc2-docstring} autostorage.merge.MergeReport.copied
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} reused
:canonical: autostorage.merge.MergeReport.reused
:type: dict[str, int]
:value: >
   None

```{autodoc2-docstring} autostorage.merge.MergeReport.reused
:parser: autodoc2_docstrings_parser
```

````

`````

````{py:function} merge_databases(target: autostorage.database.Database, source: autostorage.database.Database, *, commit: bool = True) -> autostorage.merge.MergeReport
:canonical: autostorage.merge.merge_databases

```{autodoc2-docstring} autostorage.merge.merge_databases
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _is_same_database(a: autostorage.database.Database, b: autostorage.database.Database) -> bool
:canonical: autostorage.merge._is_same_database

```{autodoc2-docstring} autostorage.merge._is_same_database
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _reflected_schema(db: autostorage.database.Database) -> dict[str, set[str]]
:canonical: autostorage.merge._reflected_schema

```{autodoc2-docstring} autostorage.merge._reflected_schema
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _check_mergeable(target: autostorage.database.Database, source: autostorage.database.Database) -> None
:canonical: autostorage.merge._check_mergeable

```{autodoc2-docstring} autostorage.merge._check_mergeable
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _mapped_classes() -> dict[str, type[sqlmodel.SQLModel]]
:canonical: autostorage.merge._mapped_classes

```{autodoc2-docstring} autostorage.merge._mapped_classes
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _ordered_models() -> list[type[sqlmodel.SQLModel]]
:canonical: autostorage.merge._ordered_models

```{autodoc2-docstring} autostorage.merge._ordered_models
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _fk_targets(cls: type[sqlmodel.SQLModel]) -> list[tuple[str, type[sqlmodel.SQLModel]]]
:canonical: autostorage.merge._fk_targets

```{autodoc2-docstring} autostorage.merge._fk_targets
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _copy_row(row: sqlmodel.SQLModel, *, id_map: dict[type[sqlmodel.SQLModel], dict[int, int]]) -> sqlmodel.SQLModel
:canonical: autostorage.merge._copy_row

```{autodoc2-docstring} autostorage.merge._copy_row
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _link_table_key_columns(cls: type[sqlmodel.SQLModel]) -> list[str] | None
:canonical: autostorage.merge._link_table_key_columns

```{autodoc2-docstring} autostorage.merge._link_table_key_columns
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _copy_table(cls: type[sqlmodel.SQLModel], rows: list[sqlmodel.SQLModel], *, target: autostorage.database.Database, id_map: dict[type[sqlmodel.SQLModel], dict[int, int]], copied: dict[str, int]) -> None
:canonical: autostorage.merge._copy_table

```{autodoc2-docstring} autostorage.merge._copy_table
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _table_count(db: autostorage.database.Database, cls: type[sqlmodel.SQLModel]) -> int
:canonical: autostorage.merge._table_count

```{autodoc2-docstring} autostorage.merge._table_count
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _copy_models(*, target: autostorage.database.Database, source: autostorage.database.Database, id_map: dict[type[sqlmodel.SQLModel], dict[int, int]], copied: dict[str, int], reused: dict[str, int]) -> None
:canonical: autostorage.merge._copy_models

```{autodoc2-docstring} autostorage.merge._copy_models
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _copy_geometries(*, target: autostorage.database.Database, source: autostorage.database.Database, id_map: dict[type[sqlmodel.SQLModel], dict[int, int]], copied: dict[str, int], reused: dict[str, int]) -> None
:canonical: autostorage.merge._copy_geometries

```{autodoc2-docstring} autostorage.merge._copy_geometries
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _copy_calculations(*, target: autostorage.database.Database, source: autostorage.database.Database, id_map: dict[type[sqlmodel.SQLModel], dict[int, int]], copied: dict[str, int], reused: dict[str, int]) -> None
:canonical: autostorage.merge._copy_calculations

```{autodoc2-docstring} autostorage.merge._copy_calculations
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _copy_stationary_points(*, target: autostorage.database.Database, source: autostorage.database.Database, id_map: dict[type[sqlmodel.SQLModel], dict[int, int]], copied: dict[str, int], reused: dict[str, int]) -> None
:canonical: autostorage.merge._copy_stationary_points

```{autodoc2-docstring} autostorage.merge._copy_stationary_points
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _copy_stages(*, target: autostorage.database.Database, source: autostorage.database.Database, id_map: dict[type[sqlmodel.SQLModel], dict[int, int]], copied: dict[str, int], reused: dict[str, int]) -> None
:canonical: autostorage.merge._copy_stages

```{autodoc2-docstring} autostorage.merge._copy_stages
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _copy_identities(*, target: autostorage.database.Database, source: autostorage.database.Database, id_map: dict[type[sqlmodel.SQLModel], dict[int, int]], copied: dict[str, int], reused: dict[str, int]) -> set[int]
:canonical: autostorage.merge._copy_identities

```{autodoc2-docstring} autostorage.merge._copy_identities
:parser: autodoc2_docstrings_parser
```
````
