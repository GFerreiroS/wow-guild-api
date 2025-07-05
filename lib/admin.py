import lib.db as db
import lib.schemas as schema


def reset_db():
    db.reset_db()


# def create_test_user():
#     # Create a test user with a known character_id


#     user_test = schema.UserCreate(
#         username="testuser",
#         password="testpassword",  # plaintext for dev only
#         character_id=1,  # must be one of the fetched roster
#     )

#     return user_test
