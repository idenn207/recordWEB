import requests
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout, QMessageBox, QTabWidget, QTextBrowser
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

from module.data_manager import loadCookies, saveCookies, getBaseUrl


class CookieManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("쿠키관리")
        self.resize(500, 400)

        main_layout = QVBoxLayout(self)

        # 1) 안내 탭 생성
        tabs = QTabWidget()
        tabs.setDocumentMode(False)

        # — 치지직 안내 탭
        chzzk_tab = QTextBrowser()
        chzzk_tab.setHtml("""
            <h3>치지직 쿠키 추출 방법</h3>
            <ol>
              <li>네이버 페이지(<code>http://www.naver.com</code>) 에 로그인</li>
              <li>F12 → Application 탭 → 좌측 Cookies → http://www.naver.com 선택</li>
              <li><code>NID_SES</code>, <code>NID_AUT</code> 값을 복사</li>
              <li>아래 폼에 붙여넣기 후 저장</li>
            </ol>
        """)

        # — 유튜브 안내 탭
        yt_tab = QTextBrowser()
        yt_tab.setOpenExternalLinks(True)
        yt_tab.setHtml("""
            <h3>유튜브 쿠키 추출 방법</h3>
            <ol>
              <li>크롬에 <a href="https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank">Get cookies.txt LOCALLY</a> 설치</li>
              <li>유튜브에 로그인 후 확장 프로그램 실행</li>
              <li>"Copy" 버튼 클릭 → 쿠키 값 복사</li>
              <li><code>recordWEB/json/ycookie.txt</code> 파일을 열어 붙여넣고 저장</li>
            </ol>
        """)

        # — 유튜브 PO토큰 안내 탭 (기존 탭 스타일 그대로 추가)
        yt_po_tab = QTextBrowser()
        yt_po_tab.setOpenExternalLinks(True)
        yt_po_tab.setHtml("""
            <h3>유튜브 PO 토큰 추출 방법</h3>
            <ol>
              <li>프로그램 경로의 ext_PoToken.bat을 실행</li>
              <li>실행 후 아무 유튜브 영상 주소를 입력</li>
              <li>생성된 po_token.txt 파일을 열어 PO토큰값 확인</li>
              <li>아래 PO토큰값 입력칸에 입력 후 저장</li>
              <li>po_token, pot_raw.txt 파일은 삭제</li>
            </ol>
            <p style="margin-top:8px;">
              ※ bgutil-pot-windows-x86_64.exe 파일이 /dependent/bgutil-pot 폴더에 <br>있는지 꼭 확인해주세요(없으면 auto_install 재실행).
              <br><br>※ PO토큰은 1~3일 마다 혹은 PO토큰 오류가 발생할 시 갱신을 권장합니다.
            </p>
        """)

        tabs.addTab(chzzk_tab, "치지직 안내")
        tabs.addTab(yt_tab, "유튜브 안내")
        tabs.addTab(yt_po_tab, "PO토큰 안내")
        main_layout.addWidget(tabs)

        # 2) 기존 폼 레이아웃
        form_layout = QFormLayout()
        self.fields = {}

        cookie_data = loadCookies()
        for key, value in cookie_data.items():
            label = QLabel(f"{key}:")
            edit  = QLineEdit(str(value))
            form_layout.addRow(label, edit)
            self.fields[key] = edit

        if not self.fields:
            form_layout.addRow(QLabel("(cookie.json에 등록된 쿠키 없음)"))

        # 유튜브 PO토큰 입력 (기존 QFormLayout 스타일 그대로 한 줄 추가)
        self.yt_po_edit = QLineEdit("")
        self.yt_po_edit.setPlaceholderText("여기에 유튜브 PO 토큰을 붙여넣기")
        form_layout.addRow(QLabel("ytPoToken:"), self.yt_po_edit)

        # 서버에서 기존 토큰을 불러와 미리 채우기 (실패해도 무시)
        try:
            base_url = getBaseUrl()
            resp = requests.get(f"{base_url}/api/yt_potoken", timeout=3)
            if resp.status_code == 200:
                data = resp.json() if isinstance(resp.json(), dict) else {}
                self.yt_po_edit.setText(str(data.get("ytPoToken", "") or ""))

        except Exception:
            pass

        main_layout.addLayout(form_layout)

        # 3) 버튼 영역
        btn_row = QHBoxLayout()
        save_btn   = QPushButton("저장")
        cancel_btn = QPushButton("취소")
        save_btn.setMinimumHeight(40)
        cancel_btn.setMinimumHeight(40)

        # 버튼 역할 지정
        save_btn.setProperty("variant", "primary")
        cancel_btn.setProperty("variant", "secondary")

        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        main_layout.addLayout(btn_row)

        # 4) 시그널 연결
        save_btn.clicked.connect(self.saveCookies)
        cancel_btn.clicked.connect(self.close)

    def saveCookies(self):
        new_data = {key: edit.text().strip() for key, edit in self.fields.items()}
        yt_po_token = self.yt_po_edit.text().strip() if hasattr(self, "yt_po_edit") else ""

        try:
            base_url = getBaseUrl()

            # 1) 치지직 쿠키 저장 (기존 동작 유지)
            cookie_saved = False
            if self.fields:
                url = f"{base_url}/cookies"
                response = requests.post(url, json=new_data)
                if response.status_code == 200:
                    cookie_saved = True
                else:
                    raise Exception(response.json().get("detail", "오류 발생"))
            else:
                cookie_saved = True  # 저장할 필드가 없으면 쿠키 저장은 스킵(오류 방지)

            # 2) 유튜브 PO토큰 저장 (config.json에 저장)
            potoken_saved = False
            try:
                resp2 = requests.post(
                    f"{base_url}/api/yt_potoken",
                    json={"ytPoToken": yt_po_token},
                    timeout=5
                )

                if resp2.status_code == 200:
                    potoken_saved = True

            except Exception:
                potoken_saved = False

            # 결과 안내
            if cookie_saved and potoken_saved:
                QMessageBox.information(self, "저장 완료", "쿠키값과 PO 토큰이 저장되었습니다.")
            elif cookie_saved and not potoken_saved:
                QMessageBox.warning(self, "부분 저장", "쿠키값은 저장되었지만 PO 토큰 저장에 실패했습니다.")
            elif (not cookie_saved) and potoken_saved:
                QMessageBox.warning(self, "부분 저장", "PO 토큰은 저장되었지만 쿠키값 저장에 실패했습니다.")
            else:
                QMessageBox.warning(self, "저장 실패", "쿠키값과 PO 토큰 저장에 실패했습니다.")

        except Exception as e:
            QMessageBox.warning(self, "오류", f"쿠키 저장 중 오류 발생: {e}")

        self.close()
