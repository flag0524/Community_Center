# 화면에 내보내는 이름·전화번호·이메일·아이디 가리기 규칙을 값으로 고정하는 시험(관리자·주민 도메인 공용)
import pytest

from app.core.masking import mask_email, mask_login_id, mask_name, mask_phone


@pytest.mark.parametrize(
    "name,masked",
    [
        ("", "*"),
        ("김", "*"),
        ("김철", "김*"),
        ("김철수", "김*수"),
        ("남궁민수", "남**수"),
        ("홍길동입니다", "홍****다"),
    ],
)
def test_이름은_첫_글자와_끝_글자만_보인다(name: str, masked: str) -> None:
    assert mask_name(name) == masked


@pytest.mark.parametrize(
    "phone,masked",
    [
        ("01012345678", "010-****-5678"),
        ("0111234567", "011-****-4567"),
        ("123456789", "****"),  # 열 자리 미만은 앞뒤도 보이지 않는다
        ("", ""),
        (None, ""),
    ],
)
def test_전화번호는_앞_세_자리와_끝_네_자리만_보인다(phone: str | None, masked: str) -> None:
    assert mask_phone(phone) == masked


@pytest.mark.parametrize(
    "email,masked",
    [("hong@example.com", "h***@example.com"), ("nomail", "***"), ("", ""), (None, "")],
)
def test_이메일은_첫_글자와_도메인만_보인다(email: str | None, masked: str) -> None:
    assert mask_email(email) == masked


@pytest.mark.parametrize(
    "login_id,masked",
    [("honggildong", "ho*********"), ("ab", "a*"), ("a", "*"), ("", "")],
)
def test_아이디는_앞_두_글자만_보이고_끝_한_글자는_항상_가린다(login_id: str, masked: str) -> None:
    assert mask_login_id(login_id) == masked
