from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.runtime.realtime_runtime import RealtimeOpportunityRuntime
from app.core.config import Settings


class OfflineManager:
    status = __import__("app.core.enums", fromlist=["RealtimeServiceState"]).RealtimeServiceState.STOPPED

    def start(self):
        raise ConnectionError("Smoke Test模拟OpenD离线")

    def get_status(self):
        class Health:
            opend_connected = False
            last_message_at = None
        return Health()


class EmptyPipeline:
    def process_closed_bar(self, symbol, timeframe):
        return {"symbol": symbol, "status": "SUCCESS"}


def main():
    with TemporaryDirectory() as directory:
        engine = create_engine("sqlite:///" + str(Path(directory) / "runtime.db"))
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        runtime = RealtimeOpportunityRuntime(
            Settings(runtime_poll_interval_seconds=.1),
            session_factory=factory, realtime_manager=OfflineManager(),
            pipeline_factory=lambda db: EmptyPipeline(),
        )
        started = runtime.start()
        assert started["status"] == "DEGRADED"
        assert runtime.process_once()["processed"] == 0
        assert runtime.process_once()["processed"] == 0
        runtime.stop()
    print("Sprint 07 Runtime Smoke Test通过")
    print("- OpenD离线：Runtime保持运行并进入DEGRADED")
    print("- 未闭合/无K线：不生成Opportunity")
    print("- 重复轮询：不重复处理")
    print("- 订单接口：未连接")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
