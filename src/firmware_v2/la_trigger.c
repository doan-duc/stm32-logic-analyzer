#include "la_trigger.h"

bool la_trigger_validate(const la_trigger_t *trigger) {
  if (trigger == 0) {
    return false;
  }
  if (trigger->type == LA_TRIGGER_EDGE && trigger->channel >= LA_CHANNEL_COUNT) {
    return false;
  }
  return true;
}
