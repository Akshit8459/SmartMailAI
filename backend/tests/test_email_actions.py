import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models.entities import Base, User, Email
from app.repositories.email_repository import EmailRepository
from datetime import datetime

@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()

@pytest.mark.asyncio
async def test_email_repository_actions(async_session: AsyncSession):
    # Setup test user and emails
    user = User(id="user_test_1", email="test@example.com", google_id="g_123")
    async_session.add(user)

    email1 = Email(
        id="msg_1",
        thread_id="th_1",
        user_id="user_test_1",
        sender_name="Alice",
        sender_email="alice@example.com",
        recipient_list="test@example.com",
        subject="Invoice for Project X",
        snippet="Please find attached invoice...",
        body_html="<p>Invoice payload</p>",
        body_text="Invoice payload",
        received_at=datetime.utcnow(),
        is_unread=True,
        is_starred=False,
        is_important=False,
        labels=["INBOX", "UNREAD"]
    )
    email2 = Email(
        id="msg_2",
        thread_id="th_2",
        user_id="user_test_1",
        sender_name="Bob",
        sender_email="bob@example.com",
        recipient_list="test@example.com",
        subject="Weekly Sync Meeting",
        snippet="Let's meet tomorrow...",
        body_html="<p>Meeting invite</p>",
        body_text="Meeting invite",
        received_at=datetime.utcnow(),
        is_unread=True,
        is_starred=False,
        is_important=False,
        labels=["INBOX", "UNREAD"]
    )
    async_session.add_all([email1, email2])
    await async_session.commit()

    repo = EmailRepository(async_session)

    # 1. Test Toggle Read
    updated_1 = await repo.toggle_read("msg_1", "user_test_1", is_unread=False)
    assert updated_1 is not None
    assert updated_1.is_unread is False
    assert "UNREAD" not in (updated_1.labels or [])

    # 2. Test Toggle Star
    starred_1 = await repo.toggle_star("msg_1", "user_test_1", is_starred=True)
    assert starred_1.is_starred is True

    # 3. Test Archive Email
    archived_2 = await repo.archive_email("msg_2", "user_test_1")
    assert "INBOX" not in (archived_2.labels or [])
    assert "ARCHIVED" in (archived_2.labels or [])

    # 4. Test Bulk Action (bulk mark read & star)
    modified_count = await repo.bulk_action(["msg_1", "msg_2"], "user_test_1", action="mark_read")
    assert modified_count == 2
