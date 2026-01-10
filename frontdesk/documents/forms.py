from django import forms
from .models import GuestDocument


class DocumentUploadForm(forms.ModelForm):
    """Form for uploading guest documents."""
    
    class Meta:
        model = GuestDocument
        fields = [
            'document_type', 'file', 'document_number',
            'issue_date', 'expiry_date', 'issuing_country', 'notes'
        ]
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'}),
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'issuing_country': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class DocumentSearchForm(forms.Form):
    """Form for searching documents."""
    
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by guest name, document number...'
        })
    )
    document_type = forms.ChoiceField(
        required=False,
        choices=[('', 'All Types')] + list(GuestDocument.DOC_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    verified = forms.ChoiceField(
        required=False,
        choices=[('', 'All'), ('true', 'Verified'), ('false', 'Not Verified')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
