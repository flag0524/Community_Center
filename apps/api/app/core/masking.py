# 이름·전화번호·이메일·로그인 아이디를 화면에 내보낼 때 가리는 공용 함수. 관리자·주민 도메인이 함께 쓴다


def mask_name(name: str) -> str:
    if len(name) <= 1:
        return "*"
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    return f"{phone[:3]}-****-{phone[-4:]}" if len(phone) >= 10 else "****"


def mask_email(email: str | None) -> str:
    if not email:
        return ""
    local, at, domain = email.partition("@")
    return f"{local[:1]}***{at}{domain}" if at else "***"


def mask_login_id(login_id: str) -> str:
    """앞 2글자만 보이고 나머지는 *이다(예 ho*****). 통째로 드러나지 않게 끝 한 글자는 항상 가린다."""
    shown = min(2, max(len(login_id) - 1, 0))
    return login_id[:shown] + "*" * (len(login_id) - shown)
