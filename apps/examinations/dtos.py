"""DTOs for examinations API responses."""

from dataclasses import dataclass


@dataclass
class ExamClashDTO:
    type: str  # room_overlap | class_overlap
    slot_id: str
    other_slot_id: str
    message: str

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "slotId": self.slot_id,
            "otherSlotId": self.other_slot_id,
            "message": self.message,
        }
