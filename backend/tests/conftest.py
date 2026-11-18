import pytest

from app.db import get_connection, init_db


@pytest.fixture
def db():
    conn = get_connection(":memory:")
    init_db(conn)

    yield conn

    conn.close()