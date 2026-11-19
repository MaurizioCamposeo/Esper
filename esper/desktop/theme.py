"""Monochrome Qt widget palettes, preserving Esper's optical-console identity."""

DARK = dict(bg="#090909", sidebar="#070707", panel="#111111", paper="#181818",
            border="#292929", strong="#444444", text="#f1f1f1", dim="#b0b0b0",
            muted="#888888", hover="#202020", accent="#eeeeee", ink="#090909")
LIGHT = dict(bg="#eeeeee", sidebar="#e7e7e7", panel="#f8f8f8", paper="#ffffff",
             border="#cecece", strong="#aaaaaa", text="#181818", dim="#505050",
             muted="#666666", hover="#dedede", accent="#222222", ink="#ffffff")


def stylesheet(light: bool) -> str:
    p = LIGHT if light else DARK
    return """
    QWidget { background: %(bg)s; color: %(text)s; font-family: "Inter", "DejaVu Sans"; font-size: 14px; }
    QMainWindow, QDialog { background: %(bg)s; }
    QWidget#sidebar { background: %(sidebar)s; border-right: 1px solid %(border)s; }
    QFrame#hero, QFrame#card, QFrame#notice, QFrame#activity { background: %(panel)s; border: 1px solid %(border)s; }
    QWidget#heroContent { background: transparent; }
    QLabel { background: transparent; border: none; }
    QLabel#brand { font-family: "DejaVu Sans Mono"; font-size: 26px; letter-spacing: 4px; }
    QLabel#title { font-size: 52px; font-weight: 300; }
    QLabel#sectionTitle { font-size: 26px; font-weight: 400; }
    QLabel#muted { color: %(muted)s; font-size: 12px; }
    QLabel#description { color: %(dim)s; font-size: 15px; }
    QLabel#filename { font-size: 16px; font-weight: 500; }
    QLabel#excerpt { color: %(dim)s; font-size: 15px; }
    QPushButton { background: transparent; border: 1px solid %(strong)s; padding: 8px 13px; min-height: 19px; text-align: center; }
    QPushButton:hover { background: %(hover)s; }
    QPushButton:focus { border-color: %(text)s; }
    QPushButton:disabled { color: %(muted)s; border-color: %(border)s; }
    QPushButton#primary { background: %(accent)s; color: %(ink)s; border-color: %(accent)s; }
    QPushButton#searchSubmit { background: %(accent)s; color: %(ink)s; border-color: %(accent)s; min-height: 22px; padding: 16px 18px; }
    QPushButton#nav { text-align: left; border: 1px solid transparent; padding: 7px 12px; }
    QPushButton#nav:checked { background: %(hover)s; border-color: %(border)s; border-left: 2px solid %(text)s; }
    QPushButton#openCard { border-color: transparent; color: %(dim)s; padding: 3px 7px; }
    QPushButton#openCard:focus, QPushButton#openCard:hover { border-color: %(strong)s; color: %(text)s; }
    QPushButton#chip { font-size: 12px; padding: 4px 9px; }
    QPushButton#chip:checked { background: %(hover)s; border-color: %(text)s; }
    QLineEdit { background: %(panel)s; border: 1px solid %(strong)s; padding: 10px 13px; selection-background-color: %(strong)s; }
    QLineEdit:focus { border-color: %(text)s; }
    QLineEdit#search { font-size: 17px; padding: 17px; }
    QComboBox { background: %(panel)s; border: 1px solid %(strong)s; padding: 7px 10px; min-width: 100px; }
    QPushButton#segment { background: %(panel)s; padding: 5px 12px; }
    QPushButton#segment:hover { background: %(hover)s; }
    QPushButton#segment:checked { background: %(accent)s; color: %(ink)s; border-color: %(accent)s; }
    QPushButton#segment:focus, QPushButton#nav:focus { border: 2px solid %(dim)s; }
    QPushButton#mapTool { padding: 3px 10px; }
    QLabel#mapTitle { font-size: 32px; font-weight: 500; }
    QWidget#tagRail { background: %(sidebar)s; }
    QComboBox QFrame { background: %(panel)s; border: 1px solid %(strong)s; }
    QComboBox QAbstractItemView { background: %(panel)s; color: %(text)s; border: 1px solid %(strong)s; outline: none; selection-background-color: %(hover)s; selection-color: %(text)s; padding: 2px; }
    QComboBox QAbstractItemView::item { min-height: 32px; padding: 0 9px; }
    QScrollArea { border: none; background: transparent; }
    QScrollBar:vertical { background: %(bg)s; width: 9px; }
    QScrollBar::handle:vertical { background: %(strong)s; min-height: 24px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QPlainTextEdit, QTextEdit { background: %(paper)s; color: %(dim)s; border: 1px solid %(border)s; font-size: 15px; padding: 18px; selection-background-color: %(strong)s; }
    QTabWidget::pane { border: none; }
    QTabBar::tab { background: %(bg)s; padding: 12px 20px; border-bottom: 1px solid %(border)s; }
    QTabBar::tab:selected { border-bottom: 1px solid %(text)s; }
    QProgressBar { border: none; background: %(border)s; min-height: 2px; max-height: 2px; }
    QProgressBar::chunk { background: %(dim)s; }
    QStatusBar { border-top: 1px solid %(border)s; color: %(dim)s; font-size: 12px; }
    QToolTip { background: %(panel)s; color: %(text)s; border: 1px solid %(strong)s; padding: 6px; }
    """ % p
