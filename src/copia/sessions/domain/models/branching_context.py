from pydantic import BaseModel

from copia.sessions.domain.models.conversation_branch import ConversationBranch
from copia.sessions.domain.models.conversation_checkpoint import ConversationCheckpoint


class BranchingContext(BaseModel):
    active_branch_id: str
    branches: list[ConversationBranch]
    checkpoint: ConversationCheckpoint | None = None
