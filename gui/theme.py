from PyQt6.QtWidgets import QApplication

LIGHT_THEME = """
/* 전체 배경/텍스트 */
QMainWindow, QDialog { background: #f6f7fb; color: #111827; }
QLabel { color: #111827; }
QCheckBox { color: #111827; }

/* 상단 툴바 */
QToolBar { background: transparent; border: none; padding: 8px 12px; }
QToolBar QPushButton {
  background: #ffffff; color: #111827;
  border-top: 1px solid transparent; border-bottom: 1px solid transparent;
  border-left: 1px solid #e5eaf3; border-right: 1px solid #e5eaf3;
  border-radius: 0; padding: 8px 12px;
}
QToolBar QPushButton:hover  { background: #eef2ff; }
QToolBar QPushButton:pressed{ background: #dbe4ff; }

/* 툴바 검색창 */
QToolBar QLineEdit {
  background: #ffffff; color: #111827;
  border: 1px solid #e5eaf3; border-radius: 0; padding: 6px 8px;
}
QToolBar QLineEdit:hover { border-color: #d6deeb; }
QToolBar QLineEdit:focus { border-color: #c7d2fe; }

/* 공통 입력 위젯 */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
  background: #ffffff; color: #111827;
  border: 1px solid #e5eaf3; border-radius: 0; padding: 6px 8px;
}
QTextBrowser {
  background: #ffffff; color: #111827;
  border: 1px solid #e5eaf3; border-radius: 0; padding: 8px 10px;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover { border-color: #d6deff; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus   { border-color: #c7d2fe; }

/* 비활성화 위젯 */
QLineEdit:disabled, QComboBox:disabled { background: #f2f2f2; color: #888888; }
QLabel#InfoHint:disabled { color: #9a9a9a; }

/* ScrollArea 기본값 */
QAbstractScrollArea { background: transparent; border: none; }
QAbstractScrollArea::viewport { background: #f6f7fb; }

/* 설정관리창 스크롤영역/컨테이너 */
QScrollArea#SettingsArea { background: transparent; border: none; }
QScrollArea#SettingsArea::viewport { background: #f9f9f9; }
#SettingsBody { background: #f9f9f9; }

/* 표/텍스트브라우저 흰색 */
QTableView, QTableWidget, QTableView::viewport, QTableWidget::viewport { background: #ffffff; }
QTextBrowser, QTextBrowser::viewport { background: #ffffff; }

/* 전역 콤보박스 */
QComboBox {
  background: #ffffff; color: #111827;
  border: 1px solid #e5eaf3; border-radius: 0; padding: 6px 8px 6px 10px;
}
QComboBox:hover { border-color: #d6deff; }
QComboBox:focus { border-color: #c7d2fe; }
QComboBox::drop-down {
  width: 30px; subcontrol-origin: padding; subcontrol-position: top right;
  border-left: 1px solid #e5eaf3; background: #eef2ff;
  border-top-right-radius: 0; border-bottom-right-radius: 0;
}
QComboBox::down-arrow {
  width: 0; height: 0; margin-right: 9px;
  border-left: 6px solid transparent; border-right: 6px solid transparent;
  border-top: 7px solid #a5b4fc;
}
QComboBox::down-arrow:on { border-top-color: #7c89e5; }
QComboBox QAbstractItemView {
  background: #ffffff; color: #111827;
  border: 1px solid #e5eaf3; border-radius: 0;
  selection-background-color: #e0e7ff; selection-color: #111827;
  outline: 0;
}
QComboBox QAbstractItemView::item { padding: 6px 10px; }

/* 대시보드 카드 */
#GlassCard { background: rgba(255,255,255,0.70); border: 1px solid #e5eaf3; border-radius: 0; }
#CardTitle { font-weight: 600; color: #334155; }
#CardValue { font-size: 15px; font-weight: 600; color: #1f2937; }
#CardSub   { font-size: 12px; color: #64748b; }

/* 진행바 */
QProgressBar {
  background: #eef2ff; border: 1px solid #e5eaf3; border-radius: 0;
  text-align: center; color: #475569;
}
QProgressBar::chunk { background: #c7d2fe; border-radius: 0; }

/* 채널 리스트 테이블 */
QHeaderView::section {
  background: #f3f4f6; color: #334155; border: 1px solid #e5eaf3;
  padding: 6px 8px; font-weight: 600; border-radius: 0;
}
QTableWidget {
  background: #ffffff; color: #111827;
  alternate-background-color: #fafafa;
  gridline-color: #e5eaf3;
  selection-background-color: #e0e7ff;
  selection-color: #111827;
}
QTableWidget::item { color: #111827; }
QTableWidget::item:hover { background: #f5f7ff; }

/* 전역 스크롤바 */
QScrollBar:vertical {
  background: #eef2ff; width: 12px; border: 1px solid #e5eaf3; border-radius: 6px; margin: 0;
}
QScrollBar::handle:vertical { background: #c7d2fe; min-height: 24px; border-radius: 6px; }
QScrollBar::handle:vertical:hover { background: #b9c6ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
  background: #eef2ff; height: 12px; border: 1px solid #e5eaf3; border-radius: 6px; margin: 0;
}
QScrollBar::handle:horizontal { background: #c7d2fe; min-width: 24px; border-radius: 6px; }
QScrollBar::handle:horizontal:hover { background: #b9c6ff; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* 버튼 */
QPushButton {
  background: #ffffff; color: #111827;
  border: 1px solid #e5eaf3; border-radius: 4px; padding: 8px 14px;
}
QPushButton:hover  { background: #f3f6ff; border-color: #d6deff; }
QPushButton:pressed{ background: #e7eeff; }
QPushButton:disabled { background: #f3f4f6; color: #9ca3af; border-color: #e5eaf3; }
QPushButton[variant="primary"] { background: #ffffff; border-color: #a5b4fc; color: #111827; }
QPushButton[variant="primary"]:hover  { background: #f3f6ff; }
QPushButton[variant="primary"]:pressed{ background: #e7eeff; }
QPushButton[variant="secondary"] { background: #ffffff; border-color: #e5eaf3; color: #111827; }
QPushButton[variant="danger"] { background: #fff5f5; border-color: #ffe4e6; color: #7f1d1d; }
QPushButton[variant="danger"]:hover  { background: #ffecec; }
QPushButton[variant="danger"]:pressed{ background: #ffdede; }
QPushButton[context="rowaction"] {
  background: #ffffff; color: #111827;
  border: 1px solid #e5eaf3; border-radius: 0; padding: 6px 10px;
}
QPushButton[context="rowaction"]:hover  { background: #f3f6ff; }
QPushButton[context="rowaction"]:pressed{ background: #e7eeff; }
QPushButton[context="rowaction"][variant="danger"] { background: #fff5f5; border-color: #ffe4e6; color: #7f1d1d; }
QPushButton[context="rowaction"][variant="danger"]:hover  { background: #ffecec; }
QPushButton[context="rowaction"][variant="danger"]:pressed{ background: #ffdede; }
QPushButton[context="rowaction"]:disabled { background: #f3f4f6; color: #c0c4ce; border-color: #e5eaf3; }

/* 탭 */
QTabWidget { background: transparent; }
QTabWidget::tab-bar { alignment: left; }
QTabWidget::pane { background: transparent; border: none; border-radius: 0; top: 0; }
QTabBar { background: transparent; }
QTabBar::tab {
  background: #eef2ff; color: #374151;
  border: 1px solid #e5eaf3; border-bottom: none;
  padding: 8px 12px; margin-right: 6px; border-radius: 0;
}
QTabBar::tab:selected { background: #ffffff; color: #111827; border-color: #e5eaf3; }
QTabBar::tab:!selected:hover { background: #f3f6ff; }

/* 도움말 라벨 */
#InfoHint { color: #64748b; font-size: 12px; }
"""

DARK_THEME = """
/* 전체 배경/텍스트 */
QMainWindow, QDialog { background: #111827; color: #f9fafb; }
QLabel { color: #f9fafb; }
QCheckBox { color: #f9fafb; }

/* 상단 툴바 */
QToolBar { background: transparent; border: none; padding: 8px 12px; }
QToolBar QPushButton {
  background: #1f2937; color: #f9fafb;
  border-top: 1px solid transparent; border-bottom: 1px solid transparent;
  border-left: 1px solid #374151; border-right: 1px solid #374151;
  border-radius: 0; padding: 8px 12px;
}
QToolBar QPushButton:hover  { background: #2d3748; }
QToolBar QPushButton:pressed{ background: #374151; }

/* 툴바 검색창 */
QToolBar QLineEdit {
  background: #1f2937; color: #f9fafb;
  border: 1px solid #374151; border-radius: 0; padding: 6px 8px;
}
QToolBar QLineEdit:hover { border-color: #4b5563; }
QToolBar QLineEdit:focus { border-color: #a5b4fc; }

/* 공통 입력 위젯 */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox {
  background: #1f2937; color: #f9fafb;
  border: 1px solid #374151; border-radius: 0; padding: 6px 8px;
}
QTextBrowser {
  background: #1f2937; color: #f9fafb;
  border: 1px solid #374151; border-radius: 0; padding: 8px 10px;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover { border-color: #4b5563; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus   { border-color: #a5b4fc; }

/* 비활성화 위젯 */
QLineEdit:disabled, QComboBox:disabled { background: #374151; color: #6b7280; }
QLabel#InfoHint:disabled { color: #6b7280; }

/* ScrollArea 기본값 */
QAbstractScrollArea { background: transparent; border: none; }
QAbstractScrollArea::viewport { background: #111827; }

/* 설정관리창 스크롤영역/컨테이너 */
QScrollArea#SettingsArea { background: transparent; border: none; }
QScrollArea#SettingsArea::viewport { background: #1a2233; }
#SettingsBody { background: #1a2233; }

/* 표/텍스트브라우저 */
QTableView, QTableWidget, QTableView::viewport, QTableWidget::viewport { background: #1f2937; }
QTextBrowser, QTextBrowser::viewport { background: #1f2937; }

/* 전역 콤보박스 */
QComboBox {
  background: #1f2937; color: #f9fafb;
  border: 1px solid #374151; border-radius: 0; padding: 6px 8px 6px 10px;
}
QComboBox:hover { border-color: #4b5563; }
QComboBox:focus { border-color: #a5b4fc; }
QComboBox::drop-down {
  width: 30px; subcontrol-origin: padding; subcontrol-position: top right;
  border-left: 1px solid #374151; background: #2d3748;
  border-top-right-radius: 0; border-bottom-right-radius: 0;
}
QComboBox::down-arrow {
  width: 0; height: 0; margin-right: 9px;
  border-left: 6px solid transparent; border-right: 6px solid transparent;
  border-top: 7px solid #a5b4fc;
}
QComboBox::down-arrow:on { border-top-color: #818cf8; }
QComboBox QAbstractItemView {
  background: #1f2937; color: #f9fafb;
  border: 1px solid #374151; border-radius: 0;
  selection-background-color: #2d3748; selection-color: #f9fafb;
  outline: 0;
}
QComboBox QAbstractItemView::item { padding: 6px 10px; }

/* 대시보드 카드 */
#GlassCard { background: rgba(31,41,55,0.70); border: 1px solid #374151; border-radius: 0; }
#CardTitle { font-weight: 600; color: #94a3b8; }
#CardValue { font-size: 15px; font-weight: 600; color: #e2e8f0; }
#CardSub   { font-size: 12px; color: #9ca3af; }

/* 진행바 */
QProgressBar {
  background: #1e293b; border: 1px solid #374151; border-radius: 0;
  text-align: center; color: #94a3b8;
}
QProgressBar::chunk { background: #a5b4fc; border-radius: 0; }

/* 채널 리스트 테이블 */
QHeaderView::section {
  background: #1e293b; color: #94a3b8; border: 1px solid #374151;
  padding: 6px 8px; font-weight: 600; border-radius: 0;
}
QTableWidget {
  background: #1f2937; color: #f9fafb;
  alternate-background-color: #1a2233;
  gridline-color: #374151;
  selection-background-color: #2d3748;
  selection-color: #f9fafb;
}
QTableWidget::item { color: #f9fafb; }
QTableWidget::item:hover { background: #2d3748; }

/* 전역 스크롤바 */
QScrollBar:vertical {
  background: #1e293b; width: 12px; border: 1px solid #374151; border-radius: 6px; margin: 0;
}
QScrollBar::handle:vertical { background: #a5b4fc; min-height: 24px; border-radius: 6px; }
QScrollBar::handle:vertical:hover { background: #818cf8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal {
  background: #1e293b; height: 12px; border: 1px solid #374151; border-radius: 6px; margin: 0;
}
QScrollBar::handle:horizontal { background: #a5b4fc; min-width: 24px; border-radius: 6px; }
QScrollBar::handle:horizontal:hover { background: #818cf8; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* 버튼 */
QPushButton {
  background: #1f2937; color: #f9fafb;
  border: 1px solid #374151; border-radius: 4px; padding: 8px 14px;
}
QPushButton:hover  { background: #2d3748; border-color: #4b5563; }
QPushButton:pressed{ background: #374151; }
QPushButton:disabled { background: #1e293b; color: #4b5563; border-color: #374151; }
QPushButton[variant="primary"] { background: #1f2937; border-color: #a5b4fc; color: #f9fafb; }
QPushButton[variant="primary"]:hover  { background: #2d3748; }
QPushButton[variant="primary"]:pressed{ background: #374151; }
QPushButton[variant="secondary"] { background: #1f2937; border-color: #374151; color: #f9fafb; }
QPushButton[variant="danger"] { background: #2d1515; border-color: #7f1d1d; color: #fca5a5; }
QPushButton[variant="danger"]:hover  { background: #3b1d1d; }
QPushButton[variant="danger"]:pressed{ background: #4a2020; }
QPushButton[context="rowaction"] {
  background: #1f2937; color: #f9fafb;
  border: 1px solid #374151; border-radius: 0; padding: 6px 10px;
}
QPushButton[context="rowaction"]:hover  { background: #2d3748; }
QPushButton[context="rowaction"]:pressed{ background: #374151; }
QPushButton[context="rowaction"][variant="danger"] { background: #2d1515; border-color: #7f1d1d; color: #fca5a5; }
QPushButton[context="rowaction"][variant="danger"]:hover  { background: #3b1d1d; }
QPushButton[context="rowaction"][variant="danger"]:pressed{ background: #4a2020; }
QPushButton[context="rowaction"]:disabled { background: #1e293b; color: #4b5563; border-color: #374151; }

/* 탭 */
QTabWidget { background: transparent; }
QTabWidget::tab-bar { alignment: left; }
QTabWidget::pane { background: transparent; border: none; border-radius: 0; top: 0; }
QTabBar { background: transparent; }
QTabBar::tab {
  background: #1e293b; color: #94a3b8;
  border: 1px solid #374151; border-bottom: none;
  padding: 8px 12px; margin-right: 6px; border-radius: 0;
}
QTabBar::tab:selected { background: #1f2937; color: #f9fafb; border-color: #374151; }
QTabBar::tab:!selected:hover { background: #2d3748; }

/* 도움말 라벨 */
#InfoHint { color: #9ca3af; font-size: 12px; }
"""


def apply_theme(app: QApplication, is_dark: bool) -> None:
    app.setStyleSheet(DARK_THEME if is_dark else LIGHT_THEME)
