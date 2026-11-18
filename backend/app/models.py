# Data contract layer
# Pydantic models define the expected shape and constraints of our data.

from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


class ListExpensesArgs(BaseModel):
    limit: int = Field(default=10, gt=0, le=100)


class PrepareDeleteArgs(BaseModel):
    expense_ids: list[int] = Field(min_length=1)

# validate incomeing data before reaching database
class ExpenseCreate(BaseModel):
    amount_cents: int = Field(gt=0)
    category: str
    currency: str = "ETB"
    description: str | None = None
    spent_on: date = Field(default_factory=date.today)
    
    
    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value):
        category = value.strip().lower()
        if not category:
            raise ValueError("Category cannot be empty.")
        
        return category
  
# repersent complete saved expense  
class Expense(BaseModel):
    id: int = Field(gt=0)
    owner_id: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)
    currency: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str | None = None
    spent_on: date
    created_at: datetime
    
    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value):
        category = value.strip().lower()
        if not category:
            raise ValueError("Category cannot be empty.")
        return category
    
# describes optional criteria for searching expense
class SearchFilters(BaseModel):
    category: str | None = None
    text: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    
    
    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value):
        if value is None:
            return None
        
        category = value.strip().lower()
        
        if not category:
            raise ValueError("Category cannot be empty.")
        
        return category
        
    @field_validator("text", mode="before")
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return None
        
        text = value.strip()
        
        if not text:
            raise ValueError("Search text cannot be empty")
        
        return text
        
        
    @model_validator(mode="after")
    def check_date_range(self):
        
        if ( 
            self.start_date is not None 
            and self.end_date is not None 
            and self.start_date > self.end_date
        ):
            
                raise ValueError("End date must be greater than start date")
        
        return self
    
    
class Period(str, Enum):
    # all (every expense ever), today, week, month, range
    ALL = 'all'
    TODAY = 'today'
    WEEK = 'week'
    MONTH = 'month'
    RANGE = 'range'
    
# expense summary for the user
class SummaryQuery(BaseModel):
    period: Period
    start_date: date | None = None
    end_date: date | None = None
    category: str | None = None
    
    @model_validator(mode="after")
    def check_date_range(self):
        if self.period == Period.RANGE:
            if self.start_date is None or self.end_date is None:
                raise ValueError("Range period require both dates. ")
        if (
            self.start_date is not None 
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("Start date cannot be after end date")
        
        return self
    
    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value):
        if value is None:
            return None

        category = value.strip().lower()

        if not category:
            raise ValueError("Category cannot be empty")

        return category
    
    
class ApprovalArgs(BaseModel):
    approval_id: int = Field(gt=0)