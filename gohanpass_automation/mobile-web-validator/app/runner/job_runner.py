import importlib.util
import sys


class JobRunner:

    async def run(self, scenario_path, page, log_callback=None):
        spec = importlib.util.spec_from_file_location("scenario", scenario_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "run"):
            raise Exception("run(page) 함수 없음")

        if log_callback and hasattr(module, "log"):
            module.log.logger = log_callback

        auth_module = sys.modules.get("scenarios._auth")
        if log_callback and auth_module and hasattr(auth_module, "log"):
            auth_module.log.logger = log_callback

        return await module.run(page)
