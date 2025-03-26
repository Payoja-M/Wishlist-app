from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_bcrypt import Bcrypt
from sqlalchemy.ext.hybrid import hybrid_property

# Initialize database and Bcrypt
db = SQLAlchemy()
bcrypt = Bcrypt()

# Define the follow relationship table
followers = db.Table('followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    # Relationship for wishlists (One user can have multiple wishlists)
    wishlists = db.relationship('Wishlist', backref='user', lazy=True)

    # Follow relationships
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic'
    )

    def set_password(self, password):
        """Hashes a plaintext password and stores it."""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Checks a plaintext password against the stored hash."""
        return bcrypt.check_password_hash(self.password_hash, password)

    # Follow/unfollow functions
    def follow(self, user):
        """Follow another user."""
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        """Unfollow a user."""
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        """Check if following another user."""
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0

    def is_followed_by(self, user):
        """Check if a user is following them."""
        return self.followers.filter(followers.c.follower_id == user.id).count() > 0

    def is_friends_with(self, user):
        """Check if both users follow each other (mutual friendship)."""
        return self.is_following(user) and self.is_followed_by(user)


class Wishlist(db.Model):
    __tablename__ = 'wishlist'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    is_public = db.Column(db.Boolean, default=False)  # Public/private wishlists
    cover_image_url = db.Column(db.String(255))

    # Relationship: One wishlist has many items
    items = db.relationship('WishlistItem', backref='wishlist', lazy=True)


class WishlistItem(db.Model):
    __tablename__ = 'wishlist_item'
    id = db.Column(db.Integer, primary_key=True)
    wishlist_id = db.Column(db.Integer, db.ForeignKey('wishlist.id'), nullable=False)
    product_name = db.Column(db.String(255), nullable=False)
    product_link = db.Column(db.String(500))
    price_range = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text)
    is_crossed_off = db.Column(db.Boolean, default=False)  # If someone bought the item

    product_image_url = db.Column(db.String(500), nullable=True)

    purchased_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    @hybrid_property
    def price(self):
        return self.price_range

    @price.setter
    def price(self, value):
        self.price_range = value

    @price.expression
    def price(cls):
        return cls.price_range

    def can_be_crossed_off_by(self, user):
        """Only friends of the wishlist owner can cross off items."""
        return self.wishlist.user.is_friends_with(user)

