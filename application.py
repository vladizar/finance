import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Storage for balance
    balance = 0

    # Store all current user holdings symbol and shares number data from DB
    holdings = db.execute("SELECT symbol, SUM(shares) AS shares FROM transactions WHERE user = :user_id GROUP BY symbol",
                           user_id=session['user_id'])

    # Iterate over holding in holdings list
    for holding in holdings:
        # Adds company name and one share price to holding
        holding.update(lookup(holding["symbol"]))

        # Adds price of all shares prices
        holding.update({"total_price": holding["price"] * holding["shares"]})

        # Increase balance
        balance += holding["total_price"]

    # Store user's cash from DB
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                       user_id=session['user_id'])[0]["cash"]

    # Increase balance
    balance += cash

    return render_template("portfolio.html", holdings=holdings, cash=cash, balance=balance)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        # Ensure shares number was submitted
        if not request.form.get("shares"):
            return apology("must provide shares number", 400)

        # Ensure shares number is correct
        if not request.form.get("shares").isdigit() or int(request.form.get("shares")) < 1:
            return apology("shares must be an integer higher than 0", 400)

        quote = lookup(request.form.get("symbol"))

        if quote == None:
            return apology("invalid symbol", 400)

        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                           user_id=session["user_id"])[0]["cash"]

        cash = cash - quote["price"] * int(request.form.get("shares"))

        if cash < 0:
            return apology("no money no honey", 400)

        # Decrease user's money
        db.execute("UPDATE 'users' SET 'cash'=:cash WHERE id = :user_id",
                    cash=cash, user_id=session["user_id"])

        # Store transaction in DB
        db.execute("INSERT INTO 'transactions' ('user', 'symbol', 'shares', 'price') VALUES (:user_id, :symbol, :shares, :price)",
                    user_id=session["user_id"], symbol=request.form.get("symbol"), shares=int(request.form.get("shares")), price=quote["price"])

        # Redirect user to main page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    available = not bool(db.execute("SELECT id FROM users WHERE username = :username",
                                     username=request.args.get("username")))

    return jsonify(available)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Store all current user holdings symbol and shares number data from DB
    transactions = db.execute("SELECT symbol, price, shares, date FROM transactions WHERE user = :user_id",
                               user_id=session['user_id'])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        quote = lookup(request.form.get("symbol"))

        if quote == None:
            return apology("invalid symbol", 400)

        # Redirect user to page with quote info
        return render_template("quoted.html", quote=quote)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Check if username is already in use
        unavailable = bool(db.execute("SELECT id FROM users WHERE username = :username",
                                      username=request.form.get("username")))
        if unavailable:
            return apology("be unique (even in usernames)", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure confirmation password was submitted and it's identical to password
        elif not request.form.get("confirmation") or request.form.get("password") != request.form.get("confirmation"):
            return apology("must provide confirmation password", 400)

        # Insert user in DB and store his ID
        user_id = db.execute("INSERT INTO 'users' ('username', 'hash') VALUES (:username, :hash)",
                           username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        # Remember which user has logged in
        session["user_id"] = user_id

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        # Ensure shares number was submitted
        if not request.form.get("shares"):
            return apology("must provide shares number", 400)

        # Store number of selling shares that user has
        shares_amount = db.execute("SELECT SUM(shares) AS shares FROM transactions WHERE user = :user_id GROUP BY symbol HAVING symbol = :symbol",
                                    user_id=session['user_id'], symbol=request.form.get("symbol"))[0]["shares"]

        if shares_amount < int(request.form.get("shares")):
            return apology("before selling something unusual you should buy that", 400)

        quote = lookup(request.form.get("symbol"))

        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                           user_id=session["user_id"])[0]["cash"]

        cash = cash + quote["price"] * int(request.form.get("shares"))

        # Increase user's money
        db.execute("UPDATE 'users' SET 'cash'=:cash WHERE id = :user_id",
                    cash=cash, user_id=session["user_id"])

        # Store transaction in DB
        db.execute("INSERT INTO 'transactions' ('user', 'symbol', 'shares', 'price') VALUES (:user_id, :symbol, :shares, :price)",
                    user_id=session["user_id"], symbol=request.form.get("symbol"), shares=-int(request.form.get("shares")), price=quote["price"])

        # Redirect user to main page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        symbols = db.execute("SELECT symbol FROM transactions WHERE user = :user_id GROUP BY symbol",
                              user_id=session["user_id"])

        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
