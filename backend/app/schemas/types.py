from typing import Annotated

from pydantic import AfterValidator, EmailStr, StringConstraints

# Emails are compared and stored lower-cased (users.email), so
# Ann@Acme.io and ann@acme.io are one account.
LowerEmail = Annotated[EmailStr, AfterValidator(str.lower)]

# A person's name as they're shown (account menu, People, Activity).
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
