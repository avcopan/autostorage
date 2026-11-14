# {py:mod}`autostorage.types`

```{py:module} autostorage.types
```

```{autodoc2-docstring} autostorage.types
:parser: autodoc2_docstrings_parser
:allowtitles:
```

## Module Contents

### Classes

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`CompressedArrayTypeDecorator <autostorage.types.CompressedArrayTypeDecorator>`
  - ```{autodoc2-docstring} autostorage.types.CompressedArrayTypeDecorator
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`Role <autostorage.types.Role>`
  - ```{autodoc2-docstring} autostorage.types.Role
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`CalcType <autostorage.types.CalcType>`
  - ```{autodoc2-docstring} autostorage.types.CalcType
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`IndexType <autostorage.types.IndexType>`
  - ```{autodoc2-docstring} autostorage.types.IndexType
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`CalcStatus <autostorage.types.CalcStatus>`
  - ```{autodoc2-docstring} autostorage.types.CalcStatus
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### Data

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`__all__ <autostorage.types.__all__>`
  - ```{autodoc2-docstring} autostorage.types.__all__
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### API

````{py:data} __all__
:canonical: autostorage.types.__all__
:value: >
   ['CalcStatus', 'CalcType', 'CompressedArrayTypeDecorator', 'IndexType', 'Role']

```{autodoc2-docstring} autostorage.types.__all__
:parser: autodoc2_docstrings_parser
```

````

`````{py:class} CompressedArrayTypeDecorator(dtype: typing.Any = np.float64, *args: typing.Any, **kwargs: typing.Any)
:canonical: autostorage.types.CompressedArrayTypeDecorator

Bases: {py:obj}`sqlalchemy.types.TypeDecorator`

```{autodoc2-docstring} autostorage.types.CompressedArrayTypeDecorator
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.types.CompressedArrayTypeDecorator.__init__
:parser: autodoc2_docstrings_parser
```

````{py:attribute} impl
:canonical: autostorage.types.CompressedArrayTypeDecorator.impl
:value: >
   None

```{autodoc2-docstring} autostorage.types.CompressedArrayTypeDecorator.impl
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} cache_ok
:canonical: autostorage.types.CompressedArrayTypeDecorator.cache_ok
:value: >
   True

```{autodoc2-docstring} autostorage.types.CompressedArrayTypeDecorator.cache_ok
:parser: autodoc2_docstrings_parser
```

````

````{py:method} process_bind_param(value: typing.Any, dialect: typing.Any) -> bytes | None
:canonical: autostorage.types.CompressedArrayTypeDecorator.process_bind_param

```{autodoc2-docstring} autostorage.types.CompressedArrayTypeDecorator.process_bind_param
:parser: autodoc2_docstrings_parser
```

````

````{py:method} process_result_value(value: bytes | None, dialect: typing.Any) -> numpy.ndarray | None
:canonical: autostorage.types.CompressedArrayTypeDecorator.process_result_value

```{autodoc2-docstring} autostorage.types.CompressedArrayTypeDecorator.process_result_value
:parser: autodoc2_docstrings_parser
```

````

`````

`````{py:class} Role()
:canonical: autostorage.types.Role

Bases: {py:obj}`enum.StrEnum`

```{autodoc2-docstring} autostorage.types.Role
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.types.Role.__init__
:parser: autodoc2_docstrings_parser
```

````{py:attribute} INPUT
:canonical: autostorage.types.Role.INPUT
:value: >
   'input'

```{autodoc2-docstring} autostorage.types.Role.INPUT
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} OUTPUT
:canonical: autostorage.types.Role.OUTPUT
:value: >
   'output'

```{autodoc2-docstring} autostorage.types.Role.OUTPUT
:parser: autodoc2_docstrings_parser
```

````

`````

`````{py:class} CalcType()
:canonical: autostorage.types.CalcType

Bases: {py:obj}`enum.StrEnum`

```{autodoc2-docstring} autostorage.types.CalcType
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.types.CalcType.__init__
:parser: autodoc2_docstrings_parser
```

````{py:attribute} OPT
:canonical: autostorage.types.CalcType.OPT
:value: >
   'optimization'

```{autodoc2-docstring} autostorage.types.CalcType.OPT
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} OPT_TS
:canonical: autostorage.types.CalcType.OPT_TS
:value: >
   'transition_optimization'

```{autodoc2-docstring} autostorage.types.CalcType.OPT_TS
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} CONFORMER
:canonical: autostorage.types.CalcType.CONFORMER
:value: >
   'conformer_search'

```{autodoc2-docstring} autostorage.types.CalcType.CONFORMER
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} SCAN
:canonical: autostorage.types.CalcType.SCAN
:value: >
   'scan'

```{autodoc2-docstring} autostorage.types.CalcType.SCAN
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} IRC
:canonical: autostorage.types.CalcType.IRC
:value: >
   'intrinsic_reaction_coordinate'

```{autodoc2-docstring} autostorage.types.CalcType.IRC
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} MEP
:canonical: autostorage.types.CalcType.MEP
:value: >
   'minimum_energy_path_search'

```{autodoc2-docstring} autostorage.types.CalcType.MEP
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} ENERGY
:canonical: autostorage.types.CalcType.ENERGY
:value: >
   'energy'

```{autodoc2-docstring} autostorage.types.CalcType.ENERGY
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} GRADIENT
:canonical: autostorage.types.CalcType.GRADIENT
:value: >
   'gradient'

```{autodoc2-docstring} autostorage.types.CalcType.GRADIENT
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} FREQUENCY
:canonical: autostorage.types.CalcType.FREQUENCY
:value: >
   'frequency'

```{autodoc2-docstring} autostorage.types.CalcType.FREQUENCY
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} THERMO
:canonical: autostorage.types.CalcType.THERMO
:value: >
   'thermochemistry'

```{autodoc2-docstring} autostorage.types.CalcType.THERMO
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} UNDEFINED
:canonical: autostorage.types.CalcType.UNDEFINED
:value: >
   'undefined'

```{autodoc2-docstring} autostorage.types.CalcType.UNDEFINED
:parser: autodoc2_docstrings_parser
```

````

`````

`````{py:class} IndexType()
:canonical: autostorage.types.IndexType

Bases: {py:obj}`enum.StrEnum`

```{autodoc2-docstring} autostorage.types.IndexType
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.types.IndexType.__init__
:parser: autodoc2_docstrings_parser
```

````{py:attribute} ENERGY
:canonical: autostorage.types.IndexType.ENERGY
:value: >
   'relative_energy'

```{autodoc2-docstring} autostorage.types.IndexType.ENERGY
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} COORDINATE
:canonical: autostorage.types.IndexType.COORDINATE
:value: >
   'reaction_coordinate'

```{autodoc2-docstring} autostorage.types.IndexType.COORDINATE
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} UNDEFINED
:canonical: autostorage.types.IndexType.UNDEFINED
:value: >
   'undefined'

```{autodoc2-docstring} autostorage.types.IndexType.UNDEFINED
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} NONE
:canonical: autostorage.types.IndexType.NONE
:value: <Multiline-String>

```{autodoc2-docstring} autostorage.types.IndexType.NONE
:parser: autodoc2_docstrings_parser
```

````

`````

`````{py:class} CalcStatus()
:canonical: autostorage.types.CalcStatus

Bases: {py:obj}`enum.StrEnum`

```{autodoc2-docstring} autostorage.types.CalcStatus
:parser: autodoc2_docstrings_parser
```

```{rubric} Initialization
```

```{autodoc2-docstring} autostorage.types.CalcStatus.__init__
:parser: autodoc2_docstrings_parser
```

````{py:attribute} PENDING
:canonical: autostorage.types.CalcStatus.PENDING
:value: >
   'pending'

```{autodoc2-docstring} autostorage.types.CalcStatus.PENDING
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} RUNNING
:canonical: autostorage.types.CalcStatus.RUNNING
:value: >
   'running'

```{autodoc2-docstring} autostorage.types.CalcStatus.RUNNING
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} SUCCEEDED
:canonical: autostorage.types.CalcStatus.SUCCEEDED
:value: >
   'succeeded'

```{autodoc2-docstring} autostorage.types.CalcStatus.SUCCEEDED
:parser: autodoc2_docstrings_parser
```

````

````{py:attribute} FAILED
:canonical: autostorage.types.CalcStatus.FAILED
:value: >
   'failed'

```{autodoc2-docstring} autostorage.types.CalcStatus.FAILED
:parser: autodoc2_docstrings_parser
```

````

`````
