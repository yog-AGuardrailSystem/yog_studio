from fastapi import APIRouter

from app.core.team_examples import TeamGroup, load_groups

router = APIRouter()


@router.get("/examples/team", response_model=list[TeamGroup])
def team_examples() -> list[TeamGroup]:
    """The engine team's example policies (groups A to R), each as a standalone program."""
    return list(load_groups())
