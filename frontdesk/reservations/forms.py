from django import forms
from django.utils import timezone
from .models import Guest, Room, Reservation, ReservationNote


class GuestForm(forms.ModelForm):
    """Form for creating/editing guests."""
    
    class Meta:
        model = Guest
        fields = [
            'first_name', 'last_name', 'email', 'phone_number',
            'passport_number', 'nationality', 'date_of_birth',
            'address', 'city', 'country', 'postal_code',
            'notes', 'vip'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'passport_number': forms.TextInput(attrs={'class': 'form-control'}),
            'nationality': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'vip': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class GuestSearchForm(forms.Form):
    """Form for searching guests."""
    
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, passport, email...'
        })
    )


class RoomForm(forms.ModelForm):
    """Form for creating/editing rooms."""
    
    class Meta:
        model = Room
        fields = [
            'room_number', 'floor', 'room_type', 'status',
            'max_guests', 'base_rate',
            'has_balcony', 'has_sea_view', 'has_kitchen'
        ]
        widgets = {
            'room_number': forms.TextInput(attrs={'class': 'form-control'}),
            'floor': forms.NumberInput(attrs={'class': 'form-control'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'max_guests': forms.NumberInput(attrs={'class': 'form-control'}),
            'base_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'has_balcony': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_sea_view': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_kitchen': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ReservationForm(forms.ModelForm):
    """Form for creating/editing reservations."""
    
    class Meta:
        model = Reservation
        fields = [
            'guest', 'room', 'check_in_date', 'check_out_date',
            'adults', 'children', 'rate_per_night', 'special_requests'
        ]
        widgets = {
            'guest': forms.Select(attrs={'class': 'form-select'}),
            'room': forms.Select(attrs={'class': 'form-select'}),
            'check_in_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'check_out_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'adults': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'children': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'rate_per_night': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'special_requests': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial rate from room if available
        if self.instance and self.instance.room and not self.instance.rate_per_night:
            self.initial['rate_per_night'] = self.instance.room.base_rate
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')
        
        if check_in and check_out:
            if check_out <= check_in:
                raise forms.ValidationError('Check-out date must be after check-in date.')
        
        return cleaned_data


class QuickReservationForm(forms.Form):
    """Quick reservation form for walk-in guests."""
    
    # Guest info
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'})
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )
    phone_number = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone'})
    )
    passport_number = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Passport Number'})
    )
    
    # Reservation info
    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(status=Room.STATUS_AVAILABLE),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    check_in_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    check_out_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    adults = forms.IntegerField(
        initial=1, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    children = forms.IntegerField(
        initial=0, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    special_requests = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set today as default check-in
        self.fields['check_in_date'].initial = timezone.now().date()
    
    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')
        
        if check_in and check_out:
            if check_out <= check_in:
                raise forms.ValidationError('Check-out date must be after check-in date.')
        
        return cleaned_data


class CheckInForm(forms.Form):
    """Form for checking in a reservation."""
    
    room = forms.ModelChoiceField(
        queryset=Room.objects.filter(status=Room.STATUS_AVAILABLE),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    access_card_number = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Access Card Number'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )


class CheckOutForm(forms.Form):
    """Form for checking out a reservation."""
    
    payment_amount = forms.DecimalField(
        required=False,
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )


class ReservationNoteForm(forms.ModelForm):
    """Form for adding notes to reservations."""
    
    class Meta:
        model = ReservationNote
        fields = ['note']
        widgets = {
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Add a note...'})
        }


class ReservationSearchForm(forms.Form):
    """Form for searching reservations."""
    
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by reservation #, guest name...'
        })
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Statuses')] + list(Reservation.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
