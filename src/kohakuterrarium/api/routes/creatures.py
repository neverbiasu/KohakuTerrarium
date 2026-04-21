"""Creature status + control routes."""

from fastapi import APIRouter, Depends, HTTPException

from kohakuterrarium.api.deps import get_manager
from kohakuterrarium.api.schemas import (
    CreatureAdd,
    ModelSwitch,
    SlashCommand,
    OutputWiringAdd,
    WireChannel,
)
from kohakuterrarium.terrarium.config import CreatureConfig

router = APIRouter()


@router.get("")
async def list_creatures(terrarium_id: str, manager=Depends(get_manager)):
    """List all creatures in a terrarium."""
    try:
        status = manager.terrarium_status(terrarium_id)
        return status.get("creatures", {})
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("")
async def add_creature(
    terrarium_id: str, req: CreatureAdd, manager=Depends(get_manager)
):
    """Add a creature to a running terrarium."""
    config = CreatureConfig(
        name=req.name,
        config_path=req.config_path,
        listen_channels=req.listen_channels,
        send_channels=req.send_channels,
    )
    try:
        name = await manager.creature_add(terrarium_id, config)
        return {"creature": name, "status": "running"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/{name}")
async def remove_creature(terrarium_id: str, name: str, manager=Depends(get_manager)):
    """Remove a creature from a running terrarium."""
    try:
        removed = await manager.creature_remove(terrarium_id, name)
        if not removed:
            raise HTTPException(404, f"Creature not found: {name}")
        return {"status": "removed"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/interrupt")
async def interrupt_creature(
    terrarium_id: str, name: str, manager=Depends(get_manager)
):
    """Interrupt a creature's current processing. Creature stays alive."""
    try:
        await manager.creature_interrupt(terrarium_id, name)
        return {"status": "interrupted", "creature": name}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{name}/jobs")
async def creature_jobs(terrarium_id: str, name: str, manager=Depends(get_manager)):
    """List running background jobs for a creature."""
    try:
        return manager.creature_get_jobs(terrarium_id, name)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/tasks/{job_id}/stop")
async def stop_creature_task(
    terrarium_id: str, name: str, job_id: str, manager=Depends(get_manager)
):
    """Stop a specific background task on a creature."""
    try:
        if await manager.creature_cancel_job(terrarium_id, name, job_id):
            return {"status": "cancelled", "job_id": job_id}
        raise HTTPException(404, f"Task not found or already completed: {job_id}")
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/promote/{job_id}")
async def promote_creature_task(
    terrarium_id: str, name: str, job_id: str, manager=Depends(get_manager)
):
    """Promote a running direct task to background on a creature."""
    try:
        runtime = manager._terrariums.get(terrarium_id)
        if not runtime:
            raise ValueError(f"Terrarium {terrarium_id} not found")
        # Accept either a creature name or "root" for the root agent.
        # Fix for bug: was calling ``runtime.get_creature(name)`` which
        # doesn't exist — creatures live in ``runtime.creatures`` dict
        # and the public accessor is ``get_creature_agent``. The old
        # call raised AttributeError that was never caught and came
        # back as a 500 Internal Server Error.
        if name == "root":
            agent = runtime.root_agent
        else:
            handle = runtime.creatures.get(name)
            agent = handle.agent if handle else None
        if agent is None:
            raise ValueError(f"Creature {name} not found")
        ok = agent._promote_handle(job_id)
        return {"status": "promoted" if ok else "not_found"}
    except (ValueError, AttributeError) as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/command")
async def execute_creature_command(
    terrarium_id: str,
    name: str,
    req: SlashCommand,
    manager=Depends(get_manager),
):
    """Execute a slash command targeting a specific creature in a terrarium.

    ``name`` may be a creature name or the literal ``"root"`` for the
    terrarium's root agent. This is the endpoint the web frontend's
    ``/compact``, ``/clear``, ``/status`` etc. buttons should hit — the
    correct agent's ``UserCommandContext`` is built at the manager
    layer so the command operates on the intended conversation.
    """
    try:
        return await manager.creature_execute_command(
            terrarium_id, name, req.command, req.args
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(500, f"Command failed: {e}")


@router.post("/{name}/model")
async def switch_creature_model(
    terrarium_id: str, name: str, req: ModelSwitch, manager=Depends(get_manager)
):
    """Switch a creature's LLM model mid-session."""
    try:
        model = manager.creature_switch_model(terrarium_id, name, req.model)
        return {"status": "switched", "creature": name, "model": model}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{name}/wire")
async def wire_channel(
    terrarium_id: str, name: str, req: WireChannel, manager=Depends(get_manager)
):
    """Wire a creature to a channel (listen or send)."""
    try:
        await manager.creature_wire(terrarium_id, name, req.channel, req.direction)
        return {"status": "wired"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/{name}/output-wiring")
async def list_output_wiring(
    terrarium_id: str, name: str, manager=Depends(get_manager)
):
    """List output_wiring edges for one creature."""
    try:
        edges = manager.creature_output_wiring_list(terrarium_id, name)
        return {"creature": name, "output_wiring": edges}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/output-wiring")
async def add_output_wiring(
    terrarium_id: str,
    name: str,
    req: OutputWiringAdd,
    manager=Depends(get_manager),
):
    """Hot-add one output_wiring edge for a creature."""
    try:
        edge = await manager.creature_output_wiring_add(
            terrarium_id,
            name,
            req.target,
            with_content=req.with_content,
            prompt=req.prompt,
            prompt_format=req.prompt_format,
        )
        return {"status": "added", "creature": name, "edge": edge}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/{name}/output-wiring/{target}")
async def remove_output_wiring(
    terrarium_id: str, name: str, target: str, manager=Depends(get_manager)
):
    """Hot-remove one output_wiring edge by target."""
    try:
        removed = await manager.creature_output_wiring_remove(
            terrarium_id, name, target
        )
        if not removed:
            raise HTTPException(
                404,
                f"No output_wiring edge found from '{name}' to '{target}'",
            )
        return {"status": "removed", "creature": name, "target": target}
    except ValueError as e:
        raise HTTPException(404, str(e))
