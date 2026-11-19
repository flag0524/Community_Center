-- 초안(미검증): 복구시험에서 복원한 DB의 핵심 건수·금액을 보여 준다. 운영 값과 사람이 대조해 결과를 기록한다(TDD 11장).
-- 읽기만 한다. 복원한 임시 서버에서만 돌린다.
SELECT 'alembic' AS item, version_num AS value FROM jori.alembic_version;
SELECT 'members' AS item, COUNT(*) AS value FROM jori.TB_MBR;
SELECT 'applications' AS item, COUNT(*) AS value FROM jori.TB_ATNLC_APLY;
SELECT 'confirmed_applications' AS item, COUNT(*) AS value FROM jori.TB_ATNLC_APLY WHERE APLY_STTS_CD = 'ES.CONFIRM';
SELECT 'payments' AS item, COUNT(*) AS value FROM jori.TB_STLM;
SELECT 'paid_amount' AS item, COALESCE(SUM(STLM_AMT), 0) AS value FROM jori.TB_STLM WHERE STLM_STTS_CD = 'PS.PAID';
SELECT 'refunds' AS item, COUNT(*) AS value FROM jori.TB_RFND;
SELECT 'refunded_amount' AS item, COALESCE(SUM(RFND_AMT), 0) AS value FROM jori.TB_RFND WHERE RFND_STTS_CD = 'RS.DONE';
SELECT 'files' AS item, COUNT(*) AS value FROM jori.TB_FILE WHERE FILE_STTS_CD <> 'FS.DELETE';
SELECT 'job_history' AS item, COUNT(*) AS value FROM jori.TB_JOB_HSTRY;
SELECT 'code_set' AS item, COUNT(*) AS value FROM jori.TB_COM_CD;
