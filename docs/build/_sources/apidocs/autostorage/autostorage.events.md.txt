# {py:mod}`autostorage.events`

```{py:module} autostorage.events
```

```{autodoc2-docstring} autostorage.events
:parser: autodoc2_docstrings_parser
:allowtitles:
```

## Module Contents

### Functions

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`_resolve_geometry <autostorage.events._resolve_geometry>`
  - ```{autodoc2-docstring} autostorage.events._resolve_geometry
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`verify_gradient_shape <autostorage.events.verify_gradient_shape>`
  - ```{autodoc2-docstring} autostorage.events.verify_gradient_shape
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`verify_hessian_shape <autostorage.events.verify_hessian_shape>`
  - ```{autodoc2-docstring} autostorage.events.verify_hessian_shape
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`invalidate_hessian_frequency_cache <autostorage.events.invalidate_hessian_frequency_cache>`
  - ```{autodoc2-docstring} autostorage.events.invalidate_hessian_frequency_cache
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_recompute_geometry_stationary_validity <autostorage.events._recompute_geometry_stationary_validity>`
  - ```{autodoc2-docstring} autostorage.events._recompute_geometry_stationary_validity
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`revalidate_geometry_orders_on_insert_update <autostorage.events.revalidate_geometry_orders_on_insert_update>`
  - ```{autodoc2-docstring} autostorage.events.revalidate_geometry_orders_on_insert_update
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`revalidate_geometry_orders_on_hessian_delete <autostorage.events.revalidate_geometry_orders_on_hessian_delete>`
  - ```{autodoc2-docstring} autostorage.events.revalidate_geometry_orders_on_hessian_delete
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`verify_geometry_immutable_fields <autostorage.events.verify_geometry_immutable_fields>`
  - ```{autodoc2-docstring} autostorage.events.verify_geometry_immutable_fields
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`compute_geometry_hash <autostorage.events.compute_geometry_hash>`
  - ```{autodoc2-docstring} autostorage.events.compute_geometry_hash
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`compute_stage_members_hash <autostorage.events.compute_stage_members_hash>`
  - ```{autodoc2-docstring} autostorage.events.compute_stage_members_hash
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`add_inchi_identities <autostorage.events.add_inchi_identities>`
  - ```{autodoc2-docstring} autostorage.events.add_inchi_identities
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`verify_stage_order_and_barrierless <autostorage.events.verify_stage_order_and_barrierless>`
  - ```{autodoc2-docstring} autostorage.events.verify_stage_order_and_barrierless
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_resolve_stage <autostorage.events._resolve_stage>`
  - ```{autodoc2-docstring} autostorage.events._resolve_stage
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`verify_stage_ts_consistency <autostorage.events.verify_stage_ts_consistency>`
  - ```{autodoc2-docstring} autostorage.events.verify_stage_ts_consistency
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### Data

````{list-table}
:class: autosummary longtable
:align: left

* - {py:obj}`__all__ <autostorage.events.__all__>`
  - ```{autodoc2-docstring} autostorage.events.__all__
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`_IMMUTABLE_GEOMETRY_FIELDS <autostorage.events._IMMUTABLE_GEOMETRY_FIELDS>`
  - ```{autodoc2-docstring} autostorage.events._IMMUTABLE_GEOMETRY_FIELDS
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
* - {py:obj}`AUTO_MANAGED_IDENTITY_ALGORITHMS <autostorage.events.AUTO_MANAGED_IDENTITY_ALGORITHMS>`
  - ```{autodoc2-docstring} autostorage.events.AUTO_MANAGED_IDENTITY_ALGORITHMS
    :parser: autodoc2_docstrings_parser
    :summary:
    ```
````

### API

````{py:data} __all__
:canonical: autostorage.events.__all__
:value: >
   ['AUTO_MANAGED_IDENTITY_ALGORITHMS', 'add_inchi_identities', 'compute_geometry_hash', 'compute_stage...

```{autodoc2-docstring} autostorage.events.__all__
:parser: autodoc2_docstrings_parser
```

````

````{py:function} _resolve_geometry(target: autostorage.models.GradientRow | autostorage.models.HessianRow | autostorage.models.StationaryPointRow) -> autostorage.models.GeometryRow | None
:canonical: autostorage.events._resolve_geometry

```{autodoc2-docstring} autostorage.events._resolve_geometry
:parser: autodoc2_docstrings_parser
```
````

````{py:function} verify_gradient_shape(mapper: sqlalchemy.orm.Mapper, connection: sqlalchemy.engine.Connection, target: autostorage.models.GradientRow) -> None
:canonical: autostorage.events.verify_gradient_shape

```{autodoc2-docstring} autostorage.events.verify_gradient_shape
:parser: autodoc2_docstrings_parser
```
````

````{py:function} verify_hessian_shape(mapper: sqlalchemy.orm.Mapper, connection: sqlalchemy.engine.Connection, target: autostorage.models.HessianRow) -> None
:canonical: autostorage.events.verify_hessian_shape

```{autodoc2-docstring} autostorage.events.verify_hessian_shape
:parser: autodoc2_docstrings_parser
```
````

````{py:function} invalidate_hessian_frequency_cache(mapper: sqlalchemy.orm.Mapper, connection: sqlalchemy.engine.Connection, target: autostorage.models.HessianRow) -> None
:canonical: autostorage.events.invalidate_hessian_frequency_cache

```{autodoc2-docstring} autostorage.events.invalidate_hessian_frequency_cache
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _recompute_geometry_stationary_validity(geometry: autostorage.models.GeometryRow, *, excluding: collections.abc.Iterable[autostorage.models.HessianRow] = ()) -> None
:canonical: autostorage.events._recompute_geometry_stationary_validity

```{autodoc2-docstring} autostorage.events._recompute_geometry_stationary_validity
:parser: autodoc2_docstrings_parser
```
````

````{py:function} revalidate_geometry_orders_on_insert_update(session: sqlmodel.Session, flush_context: typing.Any, instances: typing.Any) -> None
:canonical: autostorage.events.revalidate_geometry_orders_on_insert_update

```{autodoc2-docstring} autostorage.events.revalidate_geometry_orders_on_insert_update
:parser: autodoc2_docstrings_parser
```
````

````{py:function} revalidate_geometry_orders_on_hessian_delete(session: sqlmodel.Session, flush_context: typing.Any, instances: typing.Any) -> None
:canonical: autostorage.events.revalidate_geometry_orders_on_hessian_delete

```{autodoc2-docstring} autostorage.events.revalidate_geometry_orders_on_hessian_delete
:parser: autodoc2_docstrings_parser
```
````

````{py:data} _IMMUTABLE_GEOMETRY_FIELDS
:canonical: autostorage.events._IMMUTABLE_GEOMETRY_FIELDS
:value: >
   ('symbols', 'coordinates')

```{autodoc2-docstring} autostorage.events._IMMUTABLE_GEOMETRY_FIELDS
:parser: autodoc2_docstrings_parser
```

````

````{py:function} verify_geometry_immutable_fields(mapper: sqlalchemy.orm.Mapper, connection: sqlalchemy.engine.Connection, target: autostorage.models.GeometryRow) -> None
:canonical: autostorage.events.verify_geometry_immutable_fields

```{autodoc2-docstring} autostorage.events.verify_geometry_immutable_fields
:parser: autodoc2_docstrings_parser
```
````

````{py:function} compute_geometry_hash(mapper: sqlalchemy.orm.Mapper, connection: sqlalchemy.engine.Connection, target: autostorage.models.GeometryRow) -> None
:canonical: autostorage.events.compute_geometry_hash

```{autodoc2-docstring} autostorage.events.compute_geometry_hash
:parser: autodoc2_docstrings_parser
```
````

````{py:function} compute_stage_members_hash(mapper: sqlalchemy.orm.Mapper, connection: sqlalchemy.engine.Connection, target: autostorage.models.StageRow) -> None
:canonical: autostorage.events.compute_stage_members_hash

```{autodoc2-docstring} autostorage.events.compute_stage_members_hash
:parser: autodoc2_docstrings_parser
```
````

````{py:data} AUTO_MANAGED_IDENTITY_ALGORITHMS
:canonical: autostorage.events.AUTO_MANAGED_IDENTITY_ALGORITHMS
:type: frozenset[automol.Algorithm]
:value: >
   'frozenset(...)'

```{autodoc2-docstring} autostorage.events.AUTO_MANAGED_IDENTITY_ALGORITHMS
:parser: autodoc2_docstrings_parser
```

````

````{py:function} add_inchi_identities(session: sqlmodel.Session, flush_context: typing.Any, instances: typing.Any) -> None
:canonical: autostorage.events.add_inchi_identities

```{autodoc2-docstring} autostorage.events.add_inchi_identities
:parser: autodoc2_docstrings_parser
```
````

````{py:function} verify_stage_order_and_barrierless(mapper: sqlalchemy.orm.Mapper, connection: sqlalchemy.engine.Connection, target: autostorage.models.StepRow) -> None
:canonical: autostorage.events.verify_stage_order_and_barrierless

```{autodoc2-docstring} autostorage.events.verify_stage_order_and_barrierless
:parser: autodoc2_docstrings_parser
```
````

````{py:function} _resolve_stage(target: autostorage.models.StepRow, id_attr: str, rel_attr: str) -> autostorage.models.StageRow | None
:canonical: autostorage.events._resolve_stage

```{autodoc2-docstring} autostorage.events._resolve_stage
:parser: autodoc2_docstrings_parser
```
````

````{py:function} verify_stage_ts_consistency(mapper: sqlalchemy.orm.Mapper, connection: sqlalchemy.engine.Connection, target: autostorage.models.StepRow) -> None
:canonical: autostorage.events.verify_stage_ts_consistency

```{autodoc2-docstring} autostorage.events.verify_stage_ts_consistency
:parser: autodoc2_docstrings_parser
```
````
