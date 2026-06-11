class SuiteRunner:
    def __init__(self, job_runner):
        self.job_runner = job_runner

    async def run_all(self, scenario_paths, page, log_callback=None):
        all_results = []

        total = len(scenario_paths)

        for idx, scenario_path in enumerate(scenario_paths, start=1):
            if log_callback:
                log_callback(f"▶ [{idx}/{total}] 실행: {scenario_path}")

            try:
                result = await self.job_runner.run(
                    scenario_path,
                    page,
                    log_callback=log_callback,
                )
            except Exception as e:
                result = [("scenario_execution", f"FAIL ({e})")]
                if log_callback:
                    log_callback(f"❌ [{idx}/{total}] 실패: {e}")

            all_results.append({
                "scenario_path": scenario_path,
                "result": result,
            })

            if log_callback:
                log_callback(f"✅ [{idx}/{total}] 다음 시나리오 진행")

        return all_results
