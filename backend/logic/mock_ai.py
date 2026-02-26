import random

def simulate_3_brains(messages):
    """
    Simulates the 95% Barrier Protocol AI Check
    Takes a list of 5 messages from the rolling window deque.
    Returns a float representing the trust score.
    """
    # For demonstration, randomly return a high score with occasional drops below 0.95
    # Since it's mock, we'll give it a 20% chance to fail the check
    if random.random() < 0.2:
        return random.uniform(0.70, 0.94)
    return random.uniform(0.95, 0.99)
