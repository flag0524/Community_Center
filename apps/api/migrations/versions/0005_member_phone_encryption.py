# 회원·관리자 휴대전화번호 평문 컬럼을 암호문(회원은 검색해시도)으로 바꾸고 평문 컬럼을 지운다(v0.8, ADR-110)
import base64
import hashlib
import hmac
import os

import sqlalchemy as sa
from alembic import op
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# 마이그레이션은 그 시점의 방식을 스스로 담는다(앱 코드가 바뀌어도 이행 결과가 달라지지 않게 복사했다).
# 앱의 app/auth/crypto.py·member_phone.py와 같은 값을 만드는지는 시험이 확인한다.
MIN_SECRET_LENGTH = 32
NONCE_BYTES = 12
ASSOCIATED_DATA = b"jori:pii:v1"
SEARCH_PURPOSE = "member-phone-search"


def _key(secret: str, purpose: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), f"jori:{purpose}".encode(), hashlib.sha256).digest()


def _encrypt(secret: str, plaintext: str) -> str:
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(_key(secret, "pii-aes256")).encrypt(nonce, plaintext.encode("utf-8"), ASSOCIATED_DATA)
    return "v1:" + base64.b64encode(nonce + sealed).decode("ascii")


def _decrypt(secret: str, token: str) -> str:
    raw = base64.b64decode(token.split(":", 1)[1], validate=True)
    return (
        AESGCM(_key(secret, "pii-aes256"))
        .decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], ASSOCIATED_DATA)
        .decode()
    )


def _search_hash(secret: str, phone: str) -> str:
    return hmac.new(_key(secret, SEARCH_PURPOSE), phone.encode("utf-8"), hashlib.sha256).hexdigest()


def _secret_if_needed(needed: bool) -> str:
    """바꿀 값이 있을 때만 비밀키를 요구한다. 값이 없는 DB(새 배포·시험)는 키 없이도 올라간다."""
    secret = os.environ.get("JORI_SECRET_KEY", "")
    if needed and len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"전화번호가 들어 있는 행이 있어 JORI_SECRET_KEY({MIN_SECRET_LENGTH}자 이상)가 필요합니다. "
            "운영에서 쓰는 키와 같은 값이어야 합니다. 아무것도 바꾸지 않고 중단합니다."
        )
    return secret


def _count(table: str, column: str) -> int:
    return int(
        op.get_bind()
        .execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL"))
        .scalar_one()
    )


def upgrade() -> None:
    bind = op.get_bind()
    secret = _secret_if_needed(
        _count("TB_MBR", "MBL_TELNO") + _count("TB_MNGR", "MBL_TELNO") > 0
    )  # 변경 전에 검사한다
    op.add_column(
        "TB_MBR",
        sa.Column("MBL_TELNO_ENCPT_VL", sa.String(1024), nullable=True, comment="휴대전화번호암호화값"),
    )
    op.add_column(
        "TB_MBR",
        sa.Column("MBL_TELNO_SRCH_HASH_VL", sa.CHAR(64), nullable=True, comment="휴대전화번호검색해시값"),
    )
    op.add_column(
        "TB_MNGR",
        sa.Column("MBL_TELNO_ENCPT_VL", sa.String(1024), nullable=True, comment="휴대전화번호암호화값"),
    )
    for sn, phone in bind.execute(
        sa.text("SELECT MBR_SN, MBL_TELNO FROM TB_MBR WHERE MBL_TELNO IS NOT NULL")
    ).all():
        bind.execute(
            sa.text(
                "UPDATE TB_MBR SET MBL_TELNO_ENCPT_VL = :enc, "
                "MBL_TELNO_SRCH_HASH_VL = :hash WHERE MBR_SN = :sn"
            ),
            {"enc": _encrypt(secret, phone), "hash": _search_hash(secret, phone), "sn": sn},
        )
    for sn, phone in bind.execute(
        sa.text("SELECT MNGR_SN, MBL_TELNO FROM TB_MNGR WHERE MBL_TELNO IS NOT NULL")
    ).all():
        bind.execute(
            sa.text("UPDATE TB_MNGR SET MBL_TELNO_ENCPT_VL = :enc WHERE MNGR_SN = :sn"),
            {"enc": _encrypt(secret, phone), "sn": sn},
        )
    op.drop_column("TB_MBR", "MBL_TELNO")
    op.drop_column("TB_MNGR", "MBL_TELNO")
    op.create_index("IX_MBR_04", "TB_MBR", ["OPER_BNDL_SN", "MBL_TELNO_SRCH_HASH_VL"])


def downgrade() -> None:
    """암호문을 풀어 평문 컬럼을 되살린다. 같은 비밀키가 없으면 변경 없이 중단한다."""
    bind = op.get_bind()
    secret = _secret_if_needed(
        _count("TB_MBR", "MBL_TELNO_ENCPT_VL") + _count("TB_MNGR", "MBL_TELNO_ENCPT_VL") > 0
    )
    # 틀린 키로 풀리지 않는 값이 있으면 컬럼을 바꾸기 전에 멈추도록 복호화를 먼저 끝낸다(DDL은 되돌릴 수 없다)
    plain = {
        table: [
            (sn, _decrypt(secret, token))
            for sn, token in bind.execute(
                sa.text(f"SELECT {key}, MBL_TELNO_ENCPT_VL FROM {table} WHERE MBL_TELNO_ENCPT_VL IS NOT NULL")
            ).all()
        ]
        for table, key in (("TB_MBR", "MBR_SN"), ("TB_MNGR", "MNGR_SN"))
    }
    op.add_column("TB_MBR", sa.Column("MBL_TELNO", sa.String(11), nullable=True, comment="휴대전화번호"))
    op.add_column("TB_MNGR", sa.Column("MBL_TELNO", sa.String(11), nullable=True, comment="휴대전화번호"))
    for table, key in (("TB_MBR", "MBR_SN"), ("TB_MNGR", "MNGR_SN")):
        for sn, phone in plain[table]:
            bind.execute(
                sa.text(f"UPDATE {table} SET MBL_TELNO = :phone WHERE {key} = :sn"),
                {"phone": phone, "sn": sn},
            )
    op.drop_index("IX_MBR_04", table_name="TB_MBR")
    op.drop_column("TB_MBR", "MBL_TELNO_SRCH_HASH_VL")
    op.drop_column("TB_MBR", "MBL_TELNO_ENCPT_VL")
    op.drop_column("TB_MNGR", "MBL_TELNO_ENCPT_VL")
