# 이 배포가 맡는 운영묶음을 설정의 사이트 식별자로 찾는다. 요청이 보낸 묶음 ID는 쓰지 않는다(R26)
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.db.tables import TB_OPER_BNDL


class BundleResolver:
    """사이트 식별자 하나에 대응하는 운영묶음 일련번호를 한 번 찾아 기억한다."""

    def __init__(self, site_id: str) -> None:
        self.site_id = site_id
        self._bundle: int | None = None
        self._lock = Lock()

    def resolve(self, session: Session) -> int:
        if self._bundle is not None:
            return self._bundle
        with self._lock:
            if self._bundle is None:
                found = session.execute(
                    select(TB_OPER_BNDL.c.OPER_BNDL_SN).where(
                        TB_OPER_BNDL.c.SITE_ID == self.site_id, TB_OPER_BNDL.c.USE_YN == "Y"
                    )
                ).scalar_one_or_none()
                if found is None:
                    # 배포 설정이 잘못된 것이라 사용자 잘못이 아니다. 어떤 값이 틀렸는지는 응답에 담지 않는다.
                    raise ApiError(ErrorCode.INTERNAL_ERROR)
                self._bundle = int(found)
            return self._bundle
