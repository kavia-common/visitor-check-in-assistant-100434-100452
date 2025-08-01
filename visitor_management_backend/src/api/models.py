"""
SQLAlchemy ORM models for the Visitor Management System.
Entities: Visitor, VisitLog, Host, AdminUser.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    ForeignKey,
    func,
    Boolean,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# PUBLIC_INTERFACE
class Visitor(Base):
    """
    Visitor model.
    Stores basic visitor info and links to visit logs.
    """
    __tablename__ = "visitors"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    id_number = Column(String, nullable=True)    # e.g., ID card/passport number
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    visit_logs = relationship("VisitLog", back_populates="visitor")


# PUBLIC_INTERFACE
class Host(Base):
    """
    Host model.
    Represents hosts (employees/people being visited).
    """
    __tablename__ = "hosts"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    phone = Column(String, nullable=True)
    department = Column(String, nullable=True)

    visit_logs = relationship("VisitLog", back_populates="host")


# PUBLIC_INTERFACE
class VisitLog(Base):
    """
    VisitLog model.
    Records visitor check-in/check-out events.
    """
    __tablename__ = "visit_logs"

    id = Column(Integer, primary_key=True, index=True)
    visitor_id = Column(Integer, ForeignKey("visitors.id"), nullable=False)
    host_id = Column(Integer, ForeignKey("hosts.id"), nullable=False)
    purpose = Column(String, nullable=True)
    check_in_time = Column(DateTime(timezone=True), server_default=func.now())
    check_out_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="checked_in")  # checked_in, checked_out, cancelled, etc.

    visitor = relationship("Visitor", back_populates="visit_logs")
    host = relationship("Host", back_populates="visit_logs")


# PUBLIC_INTERFACE
class AdminUser(Base):
    """
    AdminUser model.
    System admins for the kiosk.
    """
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)     # Store hashed password, not plaintext
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
