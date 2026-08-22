"""Login: brute-force resistance and account enumeration.

Every test here fails against the pre-audit code. `/auth/login` had no rate
limit of any kind, and it returned in microseconds for a phone number with no
account versus ~100 ms for one that existed -- so the shared error message
was not actually hiding anything from anyone timing the response.
"""

import time

from sqlalchemy import select

from app.core.rate_limit import LOGIN_BY_ACCOUNT
from app.models.user import RoleEnum, User

PASSWORD = "correct-horse-battery"
WRONG = "wrong-password-entirely"


async def _login(client, phone: str, password: str):
    return await client.post("/api/v1/auth/login", json={"phone": phone, "password": password})


async def test_sixth_wrong_password_is_locked_out(client, make_password_user):
    """Five attempts per quarter hour, keyed on the account. The sixth is
    refused outright -- before the fix an attacker had unlimited attempts."""
    user = await make_password_user(PASSWORD)

    for attempt in range(5):
        response = await _login(client, user.phone, WRONG)
        assert response.status_code == 401, f"attempt {attempt} should be a plain rejection"

    response = await _login(client, user.phone, WRONG)
    assert response.status_code == 429
    assert "Retry-After" in response.headers


async def test_lockout_survives_the_correct_password(client, make_password_user):
    """The limit has to hold even once the attacker guesses right, or the
    lockout is worth nothing: the attack ends the moment they are correct."""
    user = await make_password_user(PASSWORD)
    for _ in range(6):
        await _login(client, user.phone, WRONG)

    response = await _login(client, user.phone, PASSWORD)
    assert response.status_code == 429


async def test_one_account_lockout_does_not_lock_out_another(client, make_password_user):
    """The reason the strict limit is keyed on the account and not the
    address: a school computer lab is thirty pupils behind one external IP,
    and an IP-keyed lockout would take the whole room off the site."""
    victim = await make_password_user(PASSWORD)
    classmate = await make_password_user(PASSWORD)

    for _ in range(6):
        await _login(client, victim.phone, WRONG)
    assert (await _login(client, victim.phone, WRONG)).status_code == 429

    response = await _login(client, classmate.phone, PASSWORD)
    assert response.status_code == 200, "an unrelated account must still be able to sign in"


async def test_successful_login_clears_the_window(client, make_password_user):
    """Two typos then a correct password must not leave the pupil three
    attempts short for the next fifteen minutes."""
    user = await make_password_user(PASSWORD)
    await _login(client, user.phone, WRONG)
    await _login(client, user.phone, WRONG)
    assert (await _login(client, user.phone, PASSWORD)).status_code == 200

    for _ in range(5):
        assert (await _login(client, user.phone, WRONG)).status_code == 401


async def test_unknown_account_and_wrong_password_are_indistinguishable(client, make_password_user):
    user = await make_password_user(PASSWORD)

    missing = await _login(client, "+77019999999", WRONG)
    wrong = await _login(client, user.phone, WRONG)

    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["detail"] == wrong.json()["detail"]


async def test_unknown_account_takes_comparable_time(client, make_password_user):
    """The enumeration oracle the shared message alone does not close: argon2
    takes ~100 ms, so skipping it for a non-existent account answered in
    microseconds and said plainly which numbers are registered.

    The bound is loose on purpose -- this asserts the dummy verify happens at
    all, not a constant-time guarantee CI could not hold anyway.
    """
    user = await make_password_user(PASSWORD)

    started = time.perf_counter()
    await _login(client, user.phone, WRONG)
    existing_seconds = time.perf_counter() - started

    started = time.perf_counter()
    await _login(client, "+77018888888", WRONG)
    missing_seconds = time.perf_counter() - started

    assert missing_seconds > existing_seconds / 10, (
        f"missing account answered in {missing_seconds:.4f}s vs {existing_seconds:.4f}s "
        "for an existing one -- the timing difference identifies real accounts"
    )


async def test_deactivated_account_is_not_distinguishable_either(client, make_password_user):
    """A deactivated user with the right password must get the same answer as
    a wrong password, or the endpoint confirms the account exists."""
    user = await make_password_user(PASSWORD, is_active=False)
    response = await _login(client, user.phone, PASSWORD)
    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный номер телефона или пароль"


async def test_registration_is_rate_limited_per_address(client):
    """Ten per hour per address. Unlimited registration is free storage and
    an unlimited supply of accounts to attack the rest of the API from."""
    created = 0
    for n in range(11):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "phone": f"+7702000{n:04d}",
                "password": PASSWORD,
                "first_name": "Аян",
                "last_name": "Тест",
            },
        )
        if response.status_code == 201:
            created += 1
        else:
            assert response.status_code == 429
            break
    assert created == 10


async def test_password_is_stored_as_an_argon2_hash(client, db_session, make_password_user):
    """Not a behaviour test -- a standing assertion that nobody ever swaps
    the hasher for something reversible or unsalted."""
    user = await make_password_user(PASSWORD)
    stored = await db_session.scalar(select(User.password_hash).where(User.id == user.id))
    assert stored.startswith("$argon2")
    assert PASSWORD not in stored


async def test_over_long_password_is_refused_before_hashing(client):
    """argon2 will hash whatever it is handed, so an unbounded password field
    on an unauthenticated endpoint is a CPU-exhaustion primitive."""
    response = await client.post(
        "/api/v1/auth/login", json={"phone": "+77010000001", "password": "x" * 100_000}
    )
    assert response.status_code == 422
