from typing import cast

from fastapi import APIRouter, HTTPException, Request, status

from nightwatch.adapters.docker import DockerUnavailableError
from nightwatch.models.docker_api import DockerContainer, DockerNetwork, DockerStatus
from nightwatch.services.docker_service import DockerService

router = APIRouter(prefix="/docker", tags=["docker"])


def service(request: Request) -> DockerService:
    return cast(DockerService, request.app.state.docker_service)


def unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Docker is unavailable to the Nightwatch backend.",
    )


@router.get("/status", response_model=DockerStatus)
async def get_status(request: Request) -> DockerStatus:
    return await service(request).status()


@router.get("/containers", response_model=list[DockerContainer])
async def get_containers(request: Request) -> list[DockerContainer]:
    try:
        return await service(request).containers()
    except DockerUnavailableError as exc:
        raise unavailable() from exc


@router.get("/containers/{container_id}", response_model=DockerContainer)
async def get_container(request: Request, container_id: str) -> DockerContainer:
    try:
        container = await service(request).container(container_id)
    except DockerUnavailableError as exc:
        raise unavailable() from exc
    if container is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Container was not found."
        )
    return container


@router.get("/networks", response_model=list[DockerNetwork])
async def get_networks(request: Request) -> list[DockerNetwork]:
    try:
        return await service(request).networks()
    except DockerUnavailableError as exc:
        raise unavailable() from exc
