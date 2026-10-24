"""Which articles go into the archive: the starter set and the topic themes you can grow it with."""

STARTER_ARTICLES = [
    "Ancient Rome", "Black hole", "Leonardo da Vinci", "Great Wall of China",
    "Photosynthesis", "Albert Einstein", "Mount Everest", "Apollo 11",
    "Octopus", "Volcano", "Solar System", "William Shakespeare",
    "Great Pyramid of Giza", "Coffee", "Jupiter", "DNA", "Lion", "Internet",
]

# Each theme lists "root" articles; growing the archive follows their links to related pages.
THEMES = {
    "space": {"label": "Space & Astronomy", "roots": [
        "Solar System", "Jupiter", "Saturn", "Mars", "Sun", "Moon", "Black hole",
        "Galaxy", "Milky Way", "NASA", "Apollo 11", "Astronomy", "Star", "Planet",
        "Telescope", "Big Bang"]},
    "history": {"label": "History", "roots": [
        "Ancient Rome", "Ancient Greece", "Ancient Egypt", "Roman Empire", "Middle Ages",
        "Renaissance", "World War II", "World War I", "French Revolution", "Napoleon",
        "Byzantine Empire", "Industrial Revolution"]},
    "science": {"label": "Science", "roots": [
        "Physics", "Chemistry", "Biology", "DNA", "Photosynthesis", "Evolution", "Atom",
        "Energy", "Gravity", "Cell (biology)", "Periodic table", "Electricity"]},
    "nature": {"label": "Nature & Animals", "roots": [
        "Lion", "Octopus", "Elephant", "Volcano", "Ocean", "Tiger", "Whale", "Bird",
        "Tree", "Coral reef", "Rainforest", "Insect"]},
    "art_culture": {"label": "Art & Culture", "roots": [
        "Leonardo da Vinci", "William Shakespeare", "Painting", "Music", "Film",
        "Literature", "Vincent van Gogh", "Classical music", "Sculpture", "Theatre"]},
    "technology": {"label": "Technology", "roots": [
        "Internet", "Computer", "Artificial intelligence", "Electricity", "Telephone",
        "Software", "Robotics", "Smartphone", "World Wide Web", "Semiconductor"]},
    "geography": {"label": "Geography", "roots": [
        "Mount Everest", "Great Wall of China", "Great Pyramid of Giza", "Mountain",
        "River", "Continent", "Desert", "Ocean", "Volcano", "Island", "Lake"]},
}


def is_good_article_title(title):
    """Skip lists, timelines, disambiguation pages and other non-article pages."""
    low = title.lower()
    if ":" in title or "(identifier)" in low or "(disambiguation)" in low:
        return False
    if low.startswith(("list of", "index of", "outline of", "timeline of", "history of")):
        return False
    return 1 < len(title) <= 80
