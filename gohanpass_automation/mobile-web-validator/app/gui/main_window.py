import asyncio

import re
import importlib.util
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QTextEdit,
    QLabel,
    QFrame,
    QCheckBox,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
)

from app.runner.job_runner import JobRunner
from app.runner.suite_runner import SuiteRunner
from app.core.browser import create_browser
from datetime import datetime
from app.integrations.notion_uploader import NotionUploader, NotionUploadError


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.job_runner = JobRunner()
        self.suite_runner = SuiteRunner(self.job_runner)
        self.is_running = False
        self.last_notion_payload = None

        self.setObjectName("MainWindowRoot")
        self.setWindowTitle("모바일 웹 검증 자동화")
        self.resize(1600, 1000)
        self.setMinimumSize(1400, 900)

        self.apply_style()
        self.build_ui()
        self.register_scenario_logger()
        
    def register_scenario_logger(self):
        try:
            root = Path(__file__).resolve().parents[2]
            scenario_file = root / "scenarios" / "00_auto_click.py"

            if not scenario_file.exists():
                return

            module_name = "scenario_00_auto_click"
            spec = importlib.util.spec_from_file_location(module_name, scenario_file)
            if spec is None or spec.loader is None:
                self.append_log("⚠ 시나리오 로거 연결 실패: spec 생성 실패")
                return

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            if hasattr(module, "log"):
                module.log.logger = self.append_log
                self.append_log("✅ 시나리오 로거 연결 완료: 00_auto_click.py")
            else:
                self.append_log("⚠ 시나리오 로거 연결 실패: log 함수 없음")

        except Exception as e:
            self.append_log(f"⚠ 시나리오 로거 연결 실패: {e}")

    def apply_style(self):
        self.setStyleSheet(
            """
            QWidget {
                color: #1f2937;
                font-family: "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
                font-size: 12px;
            }

            QWidget#MainWindowRoot {
                background-color: #f5f7fb;
            }

            QLabel {
                background: transparent;
            }

            #PageTitle {
                font-size: 18px;
                font-weight: 800;
                color: #111827;
            }

            #PageDesc {
                font-size: 12px;
                color: #6b7280;
            }

            #Card {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 18px;
            }

            #SectionTitle {
                font-size: 14px;
                font-weight: 700;
                color: #111827;
            }

            #SectionDesc {
                font-size: 12px;
                color: #6b7280;
            }

            QTextEdit {
                border: 1px solid #d1d5db;
                border-radius: 14px;
                background: #ffffff;
                padding: 10px;
                font-family: "Menlo", "Consolas", monospace;
                font-size: 12px;
            }

            QListWidget {
                border: 1px solid #d1d5db;
                border-radius: 12px;
                background: #ffffff;
                padding: 8px;
                outline: none;
            }

            QListWidget::item {
                min-height: 24px;
                padding: 8px 10px;
                border-radius: 10px;
            }

            QListWidget::item:selected {
                background: #e8eefc;
                color: #111827;
            }

            QPushButton {
                min-height: 40px;
                border: none;
                border-radius: 12px;
                padding: 0 16px;
                font-size: 12px;
                font-weight: 700;
            }

            QPushButton#PrimaryButton {
                background: #111827;
                color: #ffffff;
            }

            QPushButton#PrimaryButton:hover {
                background: #0f172a;
            }

            QPushButton#PrimaryButton:disabled {
                background: #9ca3af;
                color: #f3f4f6;
            }

            QPushButton#SecondaryButton {
                background: #ffffff;
                color: #111827;
                border: 1px solid #d1d5db;
            }

            QPushButton#SecondaryButton:hover {
                background: #f9fafb;
            }

            QPushButton#SecondaryButton:disabled {
                background: #f3f4f6;
                color: #9ca3af;
                border: 1px solid #e5e7eb;
            }

            QCheckBox {
                spacing: 6px;
                color: #374151;
                font-size: 12px;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }

            QLabel#MetaLabel {
                color: #6b7280;
                font-size: 11px;
            }

            QLabel#StatusIdle {
                background: #eef2ff;
                color: #4338ca;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 700;
            }

            QLabel#StatusRunning {
                background: #ecfeff;
                color: #0f766e;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 700;
            }

            QLabel#StatusDone {
                background: #ecfdf5;
                color: #15803d;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 700;
            }

            QLabel#StatusFail {
                background: #fef2f2;
                color: #b91c1c;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 700;
            }
            """
        )

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        root.addWidget(self.build_header())
        root.addLayout(self.build_body())

    def build_header(self):
        card = QFrame()
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(6)

        title = QLabel("모바일 웹 검증 자동화")
        title.setObjectName("PageTitle")

        desc = QLabel("Chrome 모바일 화면(500 x 812) 기준으로 여러 시나리오를 선택하고 순서대로 실행합니다.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(desc)

        return card

    def build_body(self):
        main_layout = QHBoxLayout()
        main_layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(16)

        right = QVBoxLayout()
        right.setSpacing(16)

        left.addWidget(self.build_scenario_card(), 7)
        left.addWidget(self.build_option_card(), 3)

        right.addWidget(self.build_log_card(), 7)
        right.addWidget(self.build_result_card(), 2)

        main_layout.addLayout(left, 5)
        main_layout.addLayout(right, 7)

        return main_layout

    def build_scenario_card(self):
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("시나리오 목록")
        title.setObjectName("SectionTitle")

        desc = QLabel("`.py` 시나리오 파일을 여러 개 추가하고, 실행 순서를 위/아래로 조정할 수 있습니다.")
        desc.setObjectName("SectionDesc")
        desc.setWordWrap(True)

        top_btn_row = QHBoxLayout()
        top_btn_row.setSpacing(10)

        self.btn_add = QPushButton("시나리오 추가")
        self.btn_add.setObjectName("SecondaryButton")
        self.btn_add.clicked.connect(self.add_scenarios)

        self.btn_delete = QPushButton("선택 삭제")
        self.btn_delete.setObjectName("SecondaryButton")
        self.btn_delete.clicked.connect(self.delete_selected_scenario)

        self.btn_clear = QPushButton("전체 비우기")
        self.btn_clear.setObjectName("SecondaryButton")
        self.btn_clear.clicked.connect(self.clear_scenarios)

        top_btn_row.addWidget(self.btn_add)
        top_btn_row.addWidget(self.btn_delete)
        top_btn_row.addWidget(self.btn_clear)

        move_btn_row = QHBoxLayout()
        move_btn_row.setSpacing(10)

        self.btn_up = QPushButton("위로")
        self.btn_up.setObjectName("SecondaryButton")
        self.btn_up.clicked.connect(self.move_up_scenario)

        self.btn_down = QPushButton("아래로")
        self.btn_down.setObjectName("SecondaryButton")
        self.btn_down.clicked.connect(self.move_down_scenario)

        self.btn_run = QPushButton("전체 실행")
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.clicked.connect(self.run_scenarios)

        move_btn_row.addWidget(self.btn_up)
        move_btn_row.addWidget(self.btn_down)
        move_btn_row.addStretch()
        move_btn_row.addWidget(self.btn_run)

        self.scenario_list = QListWidget()
        self.scenario_list.setMinimumHeight(190)
        self.scenario_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self.status_label = QLabel("대기중")
        self.status_label.setObjectName("StatusIdle")

        self.file_name_label = QLabel("선택된 시나리오 없음")
        self.file_name_label.setObjectName("MetaLabel")
        self.file_name_label.setWordWrap(True)

        status_row.addWidget(self.status_label, 0, Qt.AlignLeft)
        status_row.addWidget(self.file_name_label, 1, Qt.AlignLeft)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addLayout(top_btn_row)
        layout.addLayout(move_btn_row)
        layout.addWidget(self.scenario_list, 1)
        layout.addLayout(status_row)

        return card

    def build_option_card(self):
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("실행 옵션")
        title.setObjectName("SectionTitle")

        desc = QLabel("현재 브라우저 및 해상도는 고정값으로 동작합니다.")
        desc.setObjectName("SectionDesc")
        desc.setWordWrap(True)

        info_box = QFrame()
        info_box.setStyleSheet("""
            QFrame {
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
            }
        """)

        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setSpacing(8)

        lines = [
            "브라우저: Chrome",
            "모드: 모바일",
            "Viewport: 500 x 812",
            "위치권한: 허용",
        ]

        for text in lines:
            label = QLabel(text)
            label.setStyleSheet("font-size: 12px; color: #111827; background: transparent;")
            info_layout.addWidget(label)

        self.chk_keep_open = QCheckBox("검증 완료 후 브라우저 유지")
        self.chk_keep_open.setChecked(False)

        self.chk_screenshot = QCheckBox("스크린샷 저장")
        self.chk_screenshot.setChecked(True)

        self.chk_collect_log = QCheckBox("실행 로그 수집")
        self.chk_collect_log.setChecked(True)

        check_row = QHBoxLayout()
        check_row.setSpacing(20)
        check_row.addWidget(self.chk_keep_open)
        check_row.addWidget(self.chk_screenshot)
        check_row.addWidget(self.chk_collect_log)
        check_row.addStretch()

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(info_box)
        layout.addLayout(check_row)

        return card

    def build_result_card(self):
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("실행 결과")
        title.setObjectName("SectionTitle")

        desc = QLabel("최근 실행 기준 결과를 요약합니다.")
        desc.setObjectName("SectionDesc")
        desc.setWordWrap(True)

        result_box = QFrame()
        result_box.setStyleSheet("""
            QFrame {
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
            }
        """)

        result_layout = QVBoxLayout(result_box)
        result_layout.setContentsMargins(14, 12, 14, 12)
        result_layout.setSpacing(8)

        self.result_file_line = QLabel("마지막 실행 파일: -")
        self.result_total_line = QLabel("전체 체크 수: 0")
        self.result_pass_line = QLabel("PASS: 0")
        self.result_fail_line = QLabel("FAIL: 0")
        self.result_na_line = QLabel("N/A: 0")
        self.result_scenario_count_line = QLabel("실행 시나리오 수: 0")

        for label in [
            self.result_file_line,
            self.result_scenario_count_line,
            self.result_total_line,
            self.result_pass_line,
            self.result_fail_line,
            self.result_na_line,
        ]:
            label.setStyleSheet("font-size: 12px; color: #111827; background: transparent;")
            label.setWordWrap(True)
            result_layout.addWidget(label)

        self.btn_notion_upload = QPushButton("노션 등록")
        self.btn_notion_upload.setObjectName("PrimaryButton")
        self.btn_notion_upload.clicked.connect(self.upload_last_result_to_notion)
        self.btn_notion_upload.setEnabled(False)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(result_box)
        layout.addWidget(self.btn_notion_upload)

        return card

    def build_log_card(self):
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("실행 로그")
        title.setObjectName("SectionTitle")

        desc = QLabel("시나리오 실행 과정과 결과가 여기 표시됩니다.")
        desc.setObjectName("SectionDesc")
        desc.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(desc)

        self.btn_clear_log = QPushButton("로그 비우기")
        self.btn_clear_log.setObjectName("SecondaryButton")
        self.btn_clear_log.clicked.connect(self.clear_log)

        top_row.addLayout(title_box, 1)
        top_row.addWidget(self.btn_clear_log, 0, Qt.AlignTop)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("실행 로그가 여기에 표시됩니다.")

        layout.addLayout(top_row)
        layout.addWidget(self.log)

        return card

    def set_status_idle(self, text):
        self.status_label.setText(text)
        self.status_label.setObjectName("StatusIdle")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_status_running(self, text):
        self.status_label.setText(text)
        self.status_label.setObjectName("StatusRunning")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_status_done(self, text):
        self.status_label.setText(text)
        self.status_label.setObjectName("StatusDone")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_status_fail(self, text):
        self.status_label.setText(text)
        self.status_label.setObjectName("StatusFail")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        
    def sort_scenarios_desc(self):
        def extract_prefix_number(file_name: str) -> int:
            match = re.match(r"(\d+)", file_name)
            return int(match.group(1)) if match else -1

        items = []
        current_item_text = None

        current_item = self.scenario_list.currentItem()
        if current_item:
            current_item_text = current_item.text()

        while self.scenario_list.count() > 0:
            items.append(self.scenario_list.takeItem(0))

        items.sort(
            key=lambda item: (extract_prefix_number(item.text()), item.text().lower()),
            reverse=True
        )

        for item in items:
            self.scenario_list.addItem(item)

        if current_item_text:
            for i in range(self.scenario_list.count()):
                if self.scenario_list.item(i).text() == current_item_text:
                    self.scenario_list.setCurrentRow(i)
                    break

    def add_scenarios(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "시나리오 선택",
            "",
            "Python Files (*.py)"
        )

        if not file_paths:
            return

        added_count = 0
        existing_paths = set(self.get_scenario_paths())

        for file_path in file_paths:
            if file_path in existing_paths:
                continue

            item = QListWidgetItem(Path(file_path).name)
            item.setData(Qt.UserRole, file_path)
            item.setToolTip(file_path)
            self.scenario_list.addItem(item)
            added_count += 1

        self.sort_scenarios_desc()

        self.file_name_label.setText(f"선택된 시나리오 수: {self.scenario_list.count()}개")
        self.result_scenario_count_line.setText(f"실행 시나리오 수: {self.scenario_list.count()}")
        self.append_log(f"📂 시나리오 {added_count}개 추가")

    def delete_selected_scenario(self):
        row = self.scenario_list.currentRow()
        if row < 0:
            self.append_log("⚠ 삭제할 시나리오를 선택하세요.")
            return

        item = self.scenario_list.takeItem(row)
        if item:
            self.append_log(f"🗑 삭제: {item.text()}")

        self.file_name_label.setText(f"선택된 시나리오 수: {self.scenario_list.count()}개")
        self.result_scenario_count_line.setText(f"실행 시나리오 수: {self.scenario_list.count()}")

    def clear_scenarios(self):
        self.scenario_list.clear()
        self.file_name_label.setText("선택된 시나리오 없음")
        self.result_file_line.setText("마지막 실행 파일: -")
        self.result_scenario_count_line.setText("실행 시나리오 수: 0")
        self.result_na_line.setText("N/A: 0")
        self.append_log("🧹 시나리오 목록 초기화")

    def move_up_scenario(self):
        row = self.scenario_list.currentRow()
        if row <= 0:
            return

        item = self.scenario_list.takeItem(row)
        self.scenario_list.insertItem(row - 1, item)
        self.scenario_list.setCurrentRow(row - 1)

    def move_down_scenario(self):
        row = self.scenario_list.currentRow()
        if row < 0 or row >= self.scenario_list.count() - 1:
            return

        item = self.scenario_list.takeItem(row)
        self.scenario_list.insertItem(row + 1, item)
        self.scenario_list.setCurrentRow(row + 1)

    def get_scenario_paths(self):
        paths = []
        for i in range(self.scenario_list.count()):
            item = self.scenario_list.item(i)
            paths.append(item.data(Qt.UserRole))
        return paths

    def clear_log(self):
        self.log.clear()

    def append_log(self, text):
        self.log.append(text)

    def collect_run_screenshots(self, scenario_paths, run_started_at: float):
        root = Path(__file__).resolve().parents[2]
        output_dirs = [
            Path.cwd() / "output",
            root / "output",
            root.parent / "output",
        ]

        screenshots = []
        seen = set()
        for scenario_path in scenario_paths:
            scenario_name = Path(scenario_path).stem
            for output_dir in output_dirs:
                if not output_dir.exists():
                    continue
                for image_path in output_dir.glob(f"{scenario_name}_*.png"):
                    try:
                        if image_path.stat().st_mtime < run_started_at - 2:
                            continue
                    except OSError:
                        continue

                    resolved = image_path.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    screenshots.append(resolved)

        screenshots.sort(key=lambda path: path.stat().st_mtime)
        return [str(path) for path in screenshots]

    def write_run_log_file(self, run_id: str):
        root = Path(__file__).resolve().parents[2]
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_path = log_dir / f"notion_run_{run_id}.txt"
        log_path.write_text(self.log.toPlainText(), encoding="utf-8")
        return str(log_path)
    
    def upload_last_result_to_notion(self):
        if not self.last_notion_payload:
            self.append_log("⚠ 노션에 등록할 실행 결과가 없습니다.")
            return

        try:
            self.btn_notion_upload.setEnabled(False)
            self.append_log("📝 Notion 등록 시작")

            uploader = NotionUploader()
            uploader.upload_result(**self.last_notion_payload)

            self.append_log("✅ Notion 등록 완료")

        except NotionUploadError as e:
            self.append_log(f"❌ Notion 등록 실패: {e.user_message}")

        except Exception:
            self.append_log("❌ Notion 등록 실패: 알 수 없는 오류가 발생했습니다.")

        finally:
            self.btn_notion_upload.setEnabled(True)

    def update_button_state(self, running: bool):
        self.is_running = running
        self.btn_run.setEnabled(not running)
        self.btn_add.setEnabled(not running)
        self.btn_delete.setEnabled(not running)
        self.btn_clear.setEnabled(not running)
        self.btn_up.setEnabled(not running)
        self.btn_down.setEnabled(not running)

        if hasattr(self, "btn_notion_upload"):
            self.btn_notion_upload.setEnabled(
                (not running) and self.last_notion_payload is not None
            )

    def run_scenarios(self):
        scenario_paths = self.get_scenario_paths()

        if not scenario_paths:
            self.append_log("❌ 시나리오 파일을 먼저 추가하세요.")
            self.set_status_fail("파일 미선택")
            return

        try:
            asyncio.run(self._run_all(scenario_paths))
        except Exception as e:
            self.append_log(f"❌ 실행 오류: {e}")
            self.set_status_fail("실행 실패")
            self.update_button_state(False)

    async def _run_all(self, scenario_paths):
        self.update_button_state(True)
        self.set_status_running("실행중")
        run_started_at = datetime.now().timestamp()

        self.append_log("🚀 전체 실행 시작")
        self.append_log(f"🧩 실행 시나리오 수: {len(scenario_paths)}")
        self.append_log("📱 브라우저 설정: Chrome / 모바일 / 500x812")

        p, browser, context, page = await create_browser()

        total_pass_count = 0
        total_fail_count = 0
        total_na_count = 0
        total_check_count = 0
        last_file_name = "-"

        try:
            all_results = await self.suite_runner.run_all(
                scenario_paths,
                page,
                log_callback=self.append_log
            )

            self.append_log("===== 전체 결과 =====")

            for scenario_result in all_results:
                scenario_path = scenario_result["scenario_path"]
                result = scenario_result["result"]

                file_name = Path(scenario_path).name
                last_file_name = file_name

                self.append_log(f"📄 시나리오 결과: {file_name}")

                for name, status in result:
                    total_check_count += 1
                    status_text = str(status).upper()

                    if status_text.startswith("PASS"):
                        total_pass_count += 1
                    elif status_text.startswith(("NA", "N/A")):
                        total_na_count += 1
                    else:
                        total_fail_count += 1

                    self.append_log(f"  - {name}: {status}")

            self.result_file_line.setText(f"마지막 실행 파일: {last_file_name}")
            self.result_scenario_count_line.setText(f"실행 시나리오 수: {len(scenario_paths)}")
            self.result_total_line.setText(f"전체 체크 수: {total_check_count}")
            self.result_pass_line.setText(f"PASS: {total_pass_count}")
            self.result_fail_line.setText(f"FAIL: {total_fail_count}")
            self.result_na_line.setText(f"N/A: {total_na_count}")
            
            result_lines = []

            for scenario_result in all_results:
                scenario_path = scenario_result["scenario_path"]
                result = scenario_result["result"]

                file_name = Path(scenario_path).name
                result_lines.append(f"[{file_name}]")

                for name, status in result:
                    result_lines.append(f"- {name}: {status}")

                result_lines.append("")

            notion_status = "완료" if total_fail_count == 0 else "실패"
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            attachment_paths = []

            if self.chk_screenshot.isChecked():
                attachment_paths.extend(
                    self.collect_run_screenshots(scenario_paths, run_started_at)
                )

            if self.chk_collect_log.isChecked():
                attachment_paths.append(self.write_run_log_file(run_id))

            self.last_notion_payload = {
                "title": f"GO Hanpass 자동리포트_{run_id}",
                "version": "1.0.0",
                "platform": "WEB_CHROME",
                "pass_count": total_pass_count,
                "fail_count": total_fail_count,
                "na_count": total_na_count,
                "total_count": total_check_count,
                "status": notion_status,
                "result_text": "\n".join(result_lines),
                "attachment_paths": attachment_paths,
            }

            self.btn_notion_upload.setEnabled(True)
            self.append_log("📝 Notion 등록 준비 완료")
            self.append_log(f"📎 Notion 첨부 준비: {len(attachment_paths)}개")

            if total_fail_count > 0:
                self.set_status_fail("FAIL 포함")
            else:
                self.set_status_done("완료")

            if self.chk_keep_open.isChecked():
                self.append_log("⏸ 브라우저 유지 옵션 활성화")
                self.append_log("브라우저 확인 후 Playwright Inspector를 종료하세요.")
                await page.pause()
        


        except Exception as e:
            self.append_log(f"❌ 에러: {str(e)}")
            self.set_status_fail("실행 실패")
        finally:
            if not self.chk_keep_open.isChecked():
                await browser.close()
                await p.stop()
                self.append_log("✅ 종료")
            else:
                self.append_log("✅ 브라우저 유지 상태")

            self.update_button_state(False)
