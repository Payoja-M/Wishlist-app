import os
from flask import Flask, jsonify, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, bcrypt, User, Wishlist, WishlistItem
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'

app = Flask(__name__, instance_relative_config=True, template_folder="templates")
app.config['SECRET_KEY'] = 'supersecretkey'  # Change for production

# -- Build absolute path to instance/database.db --
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(BASE_DIR, 'instance', 'database.db')

# -- Use that absolute path in SQLAlchemy URI --
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

csrf = CSRFProtect(app)

# -- Initialize Database & Bcrypt --
db.init_app(app)
bcrypt.init_app(app)

# -- Create all tables once app context is available --
with app.app_context():
    db.create_all()

# -- Set up Flask-Login --
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    """Used by Flask-Login to get a user by their ID."""
    return User.query.get(int(user_id))

# -----------------------------------
# ROUTES
# -----------------------------------

@app.route('/')
def home():
    """Basic homepage route."""
    return render_template(url_for('login'))

# ---------- REGISTER ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered!", "danger")
            return redirect(url_for('register'))

        new_user = User(username=username, email=email)
        new_user.set_password(password)  # Hashes the password
        db.session.add(new_user)
        db.session.commit()

        flash("Account created! Please log in.", "success")
        return redirect(url_for('login'))
    
    return render_template('register.html')

# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully!", "success")
            return redirect(url_for('profile', username=user.username))
        else:
            flash("Invalid credentials", "danger")

    return render_template('login.html')

# ---------- LOGOUT ----------
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ---------- DASHBOARD ----------
@app.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    # (Optional) existing code above

    # 1. Parse min_price and max_price
    min_price = request.args.get('min_price', 0, type=int)
    max_price = request.args.get('max_price', 999999, type=int)

    # 2. Gather IDs of followed users
    followed_users = current_user.followed.all()
    followed_ids = [u.id for u in followed_users]

    # 3. Query items from followed users, exclude your own, filter by price
    items = (db.session.query(WishlistItem)
             .join(Wishlist)
             .filter(Wishlist.user_id.in_(followed_ids))
             .filter(Wishlist.user_id != current_user.id)
             .filter(WishlistItem.price_range >= min_price,
                     WishlistItem.price_range <= max_price)
             .all())

    # 4. Return the template
    return render_template('dashboard.html',
                           items=items,
                           min_price=min_price,
                           max_price=max_price)

# ---------- CREATE A WISHLIST ----------
@app.route('/wishlist/create', methods=['GET', 'POST'])
@login_required
def create_wishlist():
    if request.method == 'POST':
        name = request.form.get('name')
        is_public = (request.form.get('is_public') == "yes")  # True if checkbox is "yes"
        
        # Grab the file from the form
        cover_image_url = request.form.get('cover_image_url')

        new_wishlist = Wishlist(
            name=name,
            user_id=current_user.id,
            is_public=is_public,
            cover_image_url=cover_image_url
        )

        db.session.add(new_wishlist)
        db.session.commit()
        flash("Wishlist created successfully!", "success")
        return redirect(url_for('create_wishlist'))

    return render_template('create_wishlist.html')

# ---------- VIEW ALL WISHLISTS ----------
@app.route('/wishlist')
def view_wishlists():
    wishlists = Wishlist.query.filter_by(user_id=current_user.id).all()
    return render_template('view_wishlists.html', wishlists=wishlists)

@app.route('/wishlist/<int:wishlist_id>')
def view_wishlist(wishlist_id):
    print("DEBUG: Entered view_wishlist route with wishlist_id =", wishlist_id)
    wishlist = Wishlist.query.get_or_404(wishlist_id)

    if wishlist.is_public:
        print("DEBUG: It's public, returning wishlist_items.html")
        return render_template('wishlist_items.html', wishlist=wishlist)
    else:
        if current_user.is_authenticated and wishlist.user_id == current_user.id:
            print("DEBUG: It's private, but user is owner -> returning wishlist_items.html")
            return render_template('wishlist_items.html', wishlist=wishlist)
        else:
            print("DEBUG: It's private and user isn't owner -> flash + redirect to view_wishlists")
            owner_username = wishlist.user.username
            flash("This wishlist is private.", "danger")
            return redirect(url_for('profile', username=owner_username))
        
@app.route('/wishlist/<int:wishlist_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_wishlist(wishlist_id):
    wishlist = Wishlist.query.get_or_404(wishlist_id)

    # Only the owner can edit
    if wishlist.user_id != current_user.id:
        flash("You can't edit someone else's wishlist.", "danger")
        return redirect(url_for('view_wishlists'))

    if request.method == 'POST':
        # Grab form data
        new_name = request.form.get('name')
        new_cover_image = request.form.get('cover_image_url')
        is_public_str = request.form.get('is_public')  # e.g. "yes" or None

        # Update fields
        wishlist.name = new_name
        wishlist.cover_image_url = new_cover_image
        # If user checked the "public" box, 'is_public' will be "yes" (or whichever value you used).
        wishlist.is_public = (is_public_str == "yes")

        db.session.commit()
        flash("Wishlist updated!", "success")
        return redirect(url_for('view_wishlists'))

    # If GET request, just render the edit form
    return render_template('edit_wishlist.html', wishlist=wishlist)

@app.route('/wishlist/<int:wishlist_id>/add_item', methods=['GET', 'POST'])
@login_required
def add_item(wishlist_id):
    wishlist = Wishlist.query.get_or_404(wishlist_id)

    # Ensure only the wishlist owner can add items
    if wishlist.user_id != current_user.id:
        flash("You don't have permission to add items here.", "danger")
        return redirect(url_for('view_wishlist_items', wishlist_id=wishlist.id))

    if request.method == 'POST':
        product_name = request.form.get('product_name')
        product_link = request.form.get('product_link')
        price_range  = request.form.get('price')
        notes        = request.form.get('notes')
        product_image_url = request.form.get('product_image_url')  # NEW

        new_item = WishlistItem(
            wishlist_id=wishlist.id,
            product_name=product_name,
            product_link=product_link,
            price_range=price_range,
            notes=notes,
            product_image_url=product_image_url  # assign the new field
        )
        db.session.add(new_item)
        db.session.commit()

        flash("Item added!", "success")
        return redirect(url_for('view_wishlist_items', wishlist_id=wishlist.id))

    # If GET request, render the add_item form
    return render_template('add_item.html', wishlist=wishlist)

@app.route('/wishlist/<int:wishlist_id>/items')
def view_wishlist_items(wishlist_id):
    wishlist = Wishlist.query.get_or_404(wishlist_id)

    if not wishlist.is_public:
        # Only the owner can see it if it's private
        if not current_user.is_authenticated or wishlist.user_id != current_user.id:
            flash("This wishlist is private.", "danger")
            owner_username = wishlist.user.username  # get the wishlist owner's username
            return redirect(url_for('profile', username=owner_username))

    return render_template('wishlist_items.html', wishlist=wishlist)

@app.route('/wishlist/<int:wishlist_id>/item/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_item(wishlist_id, item_id):
    item = WishlistItem.query.get_or_404(item_id)

    # Ensure the item belongs to the logged-in user
    if item.wishlist.user_id != current_user.id:
        flash("You don't have permission to edit this item.", "danger")
        return redirect(url_for('view_wishlist_items', wishlist_id=wishlist_id))
    
    if request.method == 'POST':
        item.product_name = request.form.get('product_name')
        item.product_link = request.form.get('product_link')
        item.price_range = request.form.get('price_range')
        item.notes = request.form.get('notes')
        # NEW
        item.product_image_url = request.form.get('product_image_url')
        
        db.session.commit()
        flash("Item updated successfully!", "success")
        return redirect(url_for('view_wishlist_items', wishlist_id=wishlist_id))

    return render_template('edit_item.html', item=item)

@app.route('/wishlist/<int:wishlist_id>/delete', methods=['POST'])
def delete_wishlist(wishlist_id):
    wishlist = Wishlist.query.get_or_404(wishlist_id)

    # Example permission check
    if wishlist.user_id != current_user.id:
        return jsonify({"error": "Forbidden"}), 403
    
    # 1. Delete all items that belong to this wishlist
    for item in wishlist.items:
        db.session.delete(item)

    # Actually delete from DB
    db.session.delete(wishlist)
    db.session.commit()
    # Return 200 JSON so fetch sees response.ok == true
    return jsonify({"success": True}), 200

@app.route('/wishlist/<int:wishlist_id>/item/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(wishlist_id, item_id):
    item = WishlistItem.query.get_or_404(item_id)

    # Ensure the item belongs to the logged-in user
    if item.wishlist.user_id != current_user.id:
        flash("You don't have permission to delete this item.", "danger")
        return redirect(url_for('view_wishlist_items', wishlist_id=wishlist_id))
    
    db.session.delete(item)
    db.session.commit()
    flash("Item deleted successfully!", "success")

    return redirect(url_for('view_wishlist_items', wishlist_id=wishlist_id))

@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow_user(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash("User not found.", "danger")
        return redirect(url_for('view_wishlists'))

    if user == current_user:
        flash("You cannot follow yourself.", "danger")
        return redirect(url_for('profile', username=username))

    current_user.follow(user)
    db.session.commit()
    flash(f"You are now following {user.username}!", "success")
    return redirect(url_for('profile', username=username))

@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow_user(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash("User not found.", "danger")
        return redirect(url_for('view_wishlists'))

    current_user.unfollow(user)
    db.session.commit()
    flash(f"You have unfollowed {user.username}.", "info")
    return redirect(url_for('profile', username=username))

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    wishlists = user.wishlists  # Fetch user's wishlists
    is_following = current_user.is_following(user)

    return render_template(
        "profile.html", 
        user=user, 
        wishlists=wishlists, 
        is_following=is_following
    )

@app.route('/wishlist/public')
def view_public_wishlists():
    public_wishlists = Wishlist.query.filter_by(is_public=True).all()
    return render_template('view_wishlists.html', public_wishlists=public_wishlists)

@app.route('/cross_off/<int:item_id>', methods=['POST'])
@login_required
def cross_off_item(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    owner = item.wishlist.user  # The wishlist owner

    # Check if current_user and owner are friends
    if current_user.is_friends_with(owner):
        item.is_crossed_off = True
        item.purchased_by = current_user.id
        db.session.commit()
    return redirect(url_for('view_wishlist', wishlist_id=item.wishlist_id))

@app.route('/uncross_off/<int:item_id>', methods=['POST'])
@login_required
def uncross_off_item(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    owner = item.wishlist.user

    # Only allow "un-cross" if:
    # 1) The current user is the one who purchased it
    # 2) The current user is still friends with the owner (optional check)
    if item.purchased_by == current_user.id and current_user.is_friends_with(owner):
        item.is_crossed_off = False
        item.purchased_by = None
        db.session.commit()

    return redirect(url_for('view_wishlist', wishlist_id=item.wishlist_id))

@app.route('/browse_users', methods=['GET', 'POST'])
@login_required
def browse_users():
    query = request.form.get('search_query', '')
    if query:
        all_users = User.query.filter(
            User.username.contains(query),
            User.id != current_user.id
        ).all()
    else:
        all_users = User.query.filter(User.id != current_user.id).all()
    return render_template('browse_users.html', users=all_users, query=query)

@app.route('/profile/<username>/followers')
def view_followers(username):
    user = User.query.filter_by(username=username).first_or_404()
    # Must call .all() if 'followers' is a dynamic relationship
    followers_list = user.followers.all()
    return render_template('followers_list.html', user=user, followers_list=followers_list)

@app.route('/profile/<username>/following')
def view_following(username):
    user = User.query.filter_by(username=username).first_or_404()
    # People this user follows
    following_list = user.followed.all()
    return render_template('following_list.html', user=user, following_list=following_list)
# -----------------------------------
# RUN FLASK APP
# -----------------------------------
if __name__ == '__main__':
    app.run(debug=True)
