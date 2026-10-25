"""WatcheRobot entry point for the voice-only solo werewolf game."""
import asyncio

from watcherobot.application import ApplicationContext


async def sdk_call(function, *args, **kwargs):
    """Run a blocking SDK call without abandoning it during cancellation."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except Exception:
            pass
        raise


async def main():
    async with ApplicationContext.from_environment() as app:
        try:
            from werewolf_monitor import run_game_monitored
            from werewolf_voice import run_voice_game

            await run_game_monitored(app, sdk_call, run_voice_game)
        except asyncio.CancelledError:
            app.logger.info("应用收到取消请求。")
            raise
        except Exception:
            app.logger.exception("机器人应用终止。请处理上述错误后重新启动。")
            raise


if __name__ == "__main__":
    asyncio.run(main())
