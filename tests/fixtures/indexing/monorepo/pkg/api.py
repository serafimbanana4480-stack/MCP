from fastapi import FastAPI

app = FastAPI()


class User:
    __tablename__ = "users"


@app.get("/users")
def list_users() -> list[str]:
    return []


def test_list_users() -> None:
    assert list_users() == []
