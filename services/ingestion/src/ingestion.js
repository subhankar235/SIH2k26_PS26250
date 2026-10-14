import { ApiError } from './errors.js';
import { validateEvent } from './contracts.js';

/** Boundary validation and source authorization precede the atomic write. */
export class IngestionService {
  constructor({ store, now = Date.now }) { this.store = store; this.now = now; }

  accept(inputs, source) {
    if (!Array.isArray(inputs) || inputs.length < 1 || inputs.length > 100) {
      throw new ApiError(422, 'INVALID_BATCH', 'A batch must contain 1 to 100 events.');
    }
    const now = this.now();
    const events = inputs.map((input) => {
      const event = validateEvent(input, { now });
      if (event.sourceId !== source.sourceId || !source.types.includes(event.type)) {
        throw new ApiError(403, 'SOURCE_FORBIDDEN', 'Source is not authorized for this event.');
      }
      return event;
    });
    return this.store.acceptBatch(events);
  }
}
