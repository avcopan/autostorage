# {py:mod}`autostorage.exc`

```{py:module} autostorage.exc
```

```{autodoc2-docstring} autostorage.exc
:parser: autodoc2_docstrings_parser
:allowtitles:
```

## Module Contents

### Data

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`__all__ <autostorage.exc.__all__>`
  - ```{autodoc2-docstring} autostorage.exc.__all__
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### API

````{py:data} __all__
:canonical: autostorage.exc.__all__
:value: >
   ['DataIntegrityError', 'MissingPrimaryKeyError', 'ResultShapeError']

```{autodoc2-docstring} autostorage.exc.__all__
:parser: autodoc2_docstrings_parser
```

````

````{py:exception} DataIntegrityError()
:canonical: autostorage.exc.DataIntegrityError

Bases: {py:obj}`Exception`

```{autodoc2-docstring} autostorage.exc.DataIntegrityError
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.exc.DataIntegrityError.__init__
:parser: autodoc2_docstrings_parser
```

````

````{py:exception} ResultShapeError(model: sqlmodel.SQLModel, actual: tuple[int, ...], expected: tuple[int, ...])
:canonical: autostorage.exc.ResultShapeError

Bases: {py:obj}`Exception`

```{autodoc2-docstring} autostorage.exc.ResultShapeError
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.exc.ResultShapeError.__init__
:parser: autodoc2_docstrings_parser
```

````

````{py:exception} MissingPrimaryKeyError(rows: list[sqlmodel.SQLModel])
:canonical: autostorage.exc.MissingPrimaryKeyError

Bases: {py:obj}`Exception`

```{autodoc2-docstring} autostorage.exc.MissingPrimaryKeyError
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.exc.MissingPrimaryKeyError.__init__
:parser: autodoc2_docstrings_parser
```

````
