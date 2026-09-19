from pydantic import BaseModel, Field


class TraefikRoute(BaseModel):
    id: str
    router_name: str
    rule: str
    domains: list[str] = Field(default_factory=list)
    service_name: str | None = None
    target_port: int | None = None
    container_id: str
    container_name: str
    middleware_names: list[str] = Field(default_factory=list)
