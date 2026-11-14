# {py:mod}`autostorage.database`

```{py:module} autostorage.database
```

```{autodoc2-docstring} autostorage.database
:parser: autodoc2_docstrings_parser
:allowtitles:
```

## Module Contents

### Classes

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`Database <autostorage.database.Database>`
  - ```{autodoc2-docstring} autostorage.database.Database
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### Functions

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`merge_databases <autostorage.database.merge_databases>`
  - ```{autodoc2-docstring} autostorage.database.merge_databases
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### Data

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`__all__ <autostorage.database.__all__>`
  - ```{autodoc2-docstring} autostorage.database.__all__
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### API

````{py:data} __all__
:canonical: autostorage.database.__all__
:value: >
   ['Database', 'Select', 'SelectOfScalar', 'SelectStatement']

```{autodoc2-docstring} autostorage.database.__all__
:parser: autodoc2_docstrings_parser
```

````

`````{py:class} Database(path: str | pathlib.Path, *, echo: bool = False)
:canonical: autostorage.database.Database

```{autodoc2-docstring} autostorage.database.Database
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.database.Database.__init__
:parser: autodoc2_docstrings_parser
```

````{py:method} session() -> collections.abc.Iterator[autostorage.events.Session]
:canonical: autostorage.database.Database.session

```{autodoc2-docstring} autostorage.database.Database.session
:parser: autodoc2_docstrings_parser
```

````

````{py:method} add(row: autostorage.database.Database.add.RowT) -> None
:canonical: autostorage.database.Database.add

```{autodoc2-docstring} autostorage.database.Database.add
:parser: autodoc2_docstrings_parser
```

````

````{py:method} add_all(rows: autostorage.events.Iterable[autostorage.database.Database.add_all.RowT]) -> None
:canonical: autostorage.database.Database.add_all

```{autodoc2-docstring} autostorage.database.Database.add_all
:parser: autodoc2_docstrings_parser
```

````

````{py:method} merge(row: autostorage.database.Database.merge.RowT) -> autostorage.database.Database.merge.RowT
:canonical: autostorage.database.Database.merge

```{autodoc2-docstring} autostorage.database.Database.merge
:parser: autodoc2_docstrings_parser
```

````

````{py:method} merge_from(source_db: autostorage.database.Database, *, commit: bool = True) -> autostorage.merge.MergeReport
:canonical: autostorage.database.Database.merge_from

```{autodoc2-docstring} autostorage.database.Database.merge_from
:parser: autodoc2_docstrings_parser
```

````

````{py:method} flush() -> None
:canonical: autostorage.database.Database.flush

```{autodoc2-docstring} autostorage.database.Database.flush
:parser: autodoc2_docstrings_parser
```

````

````{py:method} commit() -> None
:canonical: autostorage.database.Database.commit

```{autodoc2-docstring} autostorage.database.Database.commit
:parser: autodoc2_docstrings_parser
```

````

````{py:method} delete(row: autostorage.database.Database.delete.RowT) -> None
:canonical: autostorage.database.Database.delete

```{autodoc2-docstring} autostorage.database.Database.delete
:parser: autodoc2_docstrings_parser
```

````

````{py:method} get_or_none(model: type[autostorage.database.Database.get_or_none.RowT], row_id: int) -> autostorage.database.Database.get_or_none.RowT | None
:canonical: autostorage.database.Database.get_or_none

```{autodoc2-docstring} autostorage.database.Database.get_or_none
:parser: autodoc2_docstrings_parser
```

````

````{py:method} get(model: type[autostorage.database.Database.get.RowT], row_id: int) -> autostorage.database.Database.get.RowT
:canonical: autostorage.database.Database.get

```{autodoc2-docstring} autostorage.database.Database.get
:parser: autodoc2_docstrings_parser
```

````

````{py:method} exec_first(stmt: autostorage.database.SelectStatement[autostorage.database.Database.exec_first.RowT]) -> autostorage.database.Database.exec_first.RowT | None
:canonical: autostorage.database.Database.exec_first

```{autodoc2-docstring} autostorage.database.Database.exec_first
:parser: autodoc2_docstrings_parser
```

````

````{py:method} exec_one(stmt: autostorage.database.SelectStatement[autostorage.database.Database.exec_one.RowT]) -> autostorage.database.Database.exec_one.RowT
:canonical: autostorage.database.Database.exec_one

```{autodoc2-docstring} autostorage.database.Database.exec_one
:parser: autodoc2_docstrings_parser
```

````

````{py:method} exec_all(stmt: autostorage.database.SelectStatement[autostorage.database.Database.exec_all.RowT]) -> list[autostorage.database.Database.exec_all.RowT]
:canonical: autostorage.database.Database.exec_all

```{autodoc2-docstring} autostorage.database.Database.exec_all
:parser: autodoc2_docstrings_parser
```

````

````{py:method} exists(stmt: autostorage.database.SelectStatement[autostorage.database.Database.exists.RowT]) -> bool
:canonical: autostorage.database.Database.exists

```{autodoc2-docstring} autostorage.database.Database.exists
:parser: autodoc2_docstrings_parser
```

````

````{py:method} close() -> None
:canonical: autostorage.database.Database.close

```{autodoc2-docstring} autostorage.database.Database.close
:parser: autodoc2_docstrings_parser
```

````

````{py:method} __enter__() -> autostorage.models.Self
:canonical: autostorage.database.Database.__enter__

```{autodoc2-docstring} autostorage.database.Database.__enter__
:parser: autodoc2_docstrings_parser
```

````

````{py:method} __exit__(exc_type: type[BaseException] | None, exc_value: object, traceback: types.TracebackType | None) -> None
:canonical: autostorage.database.Database.__exit__

```{autodoc2-docstring} autostorage.database.Database.__exit__
:parser: autodoc2_docstrings_parser
```

````

`````

````{py:function} merge_databases(target: pathlib.Path, source: pathlib.Path) -> None
:canonical: autostorage.database.merge_databases

```{autodoc2-docstring} autostorage.database.merge_databases
:parser: autodoc2_docstrings_parser
```
````
