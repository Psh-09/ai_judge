from fastapi import APIRouter, Request

from app.schemas.rule import Rule

router = APIRouter(tags=["rules"])


@router.get("/rules", operation_id="listRules", response_model=list[Rule])
def list_rules(request: Request) -> list[Rule]:
    catalog = request.app.state.rule_catalog
    return catalog.active_rules()
