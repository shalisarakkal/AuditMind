from typing import Annotated

from pydantic import AfterValidator, EmailStr

# Emails are compared and stored lower-cased (users.email), so
# Ann@Acme.io and ann@acme.io are one account.
LowerEmail = Annotated[EmailStr, AfterValidator(str.lower)]
