# Database

The `autostorage.database` module provides SQLite database connection management through the `Database` class.

## Overview

The `Database` class is a lightweight wrapper around SQLAlchemy's engine and session management, configured for SQLite with:

- **Foreign key enforcement** — SQLite's `PRAGMA foreign_keys=ON` is automatically enabled
- **Thread safety** — `check_same_thread=False` allows multi-threaded access
- **Canonical JSON serialization** — JSON column comparisons work regardless of dict key order
- **Automatic schema creation** — All SQLModel tables are created on initialization

## Creating a Database

```python
from autostorage.database import Database

# Create or connect to a database
db = Database("path/to/database.db")

# Enable SQL logging for debugging
db = Database("path/to/database.db", echo=True)
```

The database file is created if it doesn't exist. All tables defined in `autostorage.models` are automatically created via SQLModel metadata.

## Using Sessions

Sessions manage transactions and provide the query interface. Always use sessions as context managers to ensure proper cleanup:

```python
from autostorage.database import Database
from autostorage.models import GeometryRow

db = Database("molecules.db")

# Create a session context
with db.session() as session:
    # Add a geometry
    geom = GeometryRow(symbols=["C", "H", "H", "H", "H"], coordinates=[[0.0, 0.0, 0.0], ...])
    session.add(geom)
    session.commit()  # Explicitly commit changes
    
    # Query geometries
    results = session.exec(select(GeometryRow)).all()
```

**Important**: Each call to `db.session()` creates a **new** session. Nothing is committed automatically — you must call `session.commit()` to persist changes.

### Session Lifecycle

```python
with db.session() as session:
    # Add/modify rows
    session.add(row)
    
    # Flush to DB without committing (assigns IDs, checks constraints)
    session.flush()
    
    # Commit the transaction
    session.commit()
    
# Session is automatically closed here
```

For more details on session usage, querying, transaction control, and advanced patterns, see the [SQLAlchemy Session documentation](https://docs.sqlalchemy.org/en/21/orm/session_basics.html).

## Closing the Database

When finished with a database, dispose of the connection pool:

```python
db.close()
```

This is typically unnecessary for short-lived scripts but recommended for long-running applications.
